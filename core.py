"""Streaming XML index and byte-preserving attribute editor. No game dependencies."""
from __future__ import annotations

import gzip
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time
from xml.parsers import expat
from xml.sax.saxutils import escape

VERSION = 1
CHUNK = 1024 * 1024
PAGE = 200
ATTR = re.compile(rb'''([^\s=<>/]+)\s*=\s*(["'])(.*?)\2''', re.S)


def parser():
    p = expat.ParserCreate()
    def forbidden(*args):
        raise ValueError('不支持 DTD 或外部实体')
    p.StartDoctypeDeclHandler = forbidden
    p.ExternalEntityRefHandler = forbidden
    def declaration(version, encoding, standalone):
        if encoding and encoding.lower().replace('-', '') != 'utf8':
            raise ValueError('仅支持 UTF-8 X4 存档')
    p.XmlDeclHandler = declaration
    return p


def input_stream(path):
    with open(path, 'rb') as f:
        zipped = f.read(2) == b'\x1f\x8b'
    return gzip.open(path, 'rb') if zipped else open(path, 'rb')


def fingerprint(path):
    path = Path(path).resolve()
    s = path.stat()
    return [str(path), s.st_size, s.st_mtime_ns, VERSION]


def connect(folder):
    db = sqlite3.connect((Path(folder) / 'index.db').resolve().as_uri() + '?mode=ro', uri=True)
    db.execute('PRAGMA cache_size=-8192')
    return closing(db)


def build_index(source, cache_root, progress=lambda msg: None):
    """Parse EVERY XML element, spool exact XML and index its parent and byte offset."""
    started = time.perf_counter()
    fp = fingerprint(source)
    key = hashlib.sha256(json.dumps(fp).encode()).hexdigest()[:24]
    root = Path(cache_root)
    root.mkdir(parents=True, exist_ok=True)
    dest = root / key
    if (dest / 'meta.json').exists():
        meta = json.loads((dest / 'meta.json').read_text('utf-8'))
        if meta['fingerprint'] == fp and (dest / 'index.db').exists() and (dest / 'source.xml').stat().st_size == meta['xml_bytes']:
            progress('复用已完成的磁盘索引')
            return str(dest), meta
    # Publish a small completion marker, rather than rename a multi-GB directory.
    # On Windows directory rename can trigger lengthy filesystem/security scans.
    if dest.exists():
        raise ValueError('存在不完整缓存，请关闭程序后清理 .cache 对应目录')
    dest.mkdir()
    work = dest
    completed = False
    db = None
    try:
        db = sqlite3.connect(work / 'index.db')
        db.executescript('''PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
            PRAGMA cache_size=-32768; PRAGMA temp_store=FILE;
            CREATE TABLE nodes(id INTEGER PRIMARY KEY, parent INTEGER NOT NULL,
                               tag INTEGER NOT NULL, offset INTEGER NOT NULL);
            CREATE TABLE tags(id INTEGER PRIMARY KEY, name TEXT UNIQUE, count INTEGER);
            CREATE TABLE labels(node INTEGER PRIMARY KEY, ref TEXT, label TEXT);
        ''')
        p = parser()
        stack, batch, labels = [], [], []
        tags, counts = {}, {}
        count = 0
        def flush():
            db.executemany('INSERT INTO nodes VALUES(?,?,?,?)', batch)
            db.executemany('INSERT INTO labels VALUES(?,?,?)', labels)
            batch.clear()
            labels.clear()
        def start(tag, attrs):
            nonlocal count
            count += 1
            tid = tags.setdefault(tag, len(tags) + 1)
            counts[tid] = counts.get(tid, 0) + 1
            batch.append((count, stack[-1] if stack else 0, tid, p.CurrentByteIndex))
            stack.append(count)
            # Sparse descriptive index; attributes themselves stay in the source XML.
            ref = attrs.get('id')
            parts = [f'{k}={attrs[k][:180]}' for k in ('name', 'class', 'macro', 'owner', 'ware', 'faction') if k in attrs]
            if ref is not None or parts:
                labels.append((count, ref, ' | '.join(parts)[:600]))
            if len(batch) >= 20000:
                flush()
        p.StartElementHandler = start
        p.EndElementHandler = lambda tag: stack.pop()
        size = 0
        digest = hashlib.sha256()
        last = 0
        with input_stream(source) as src, open(work / 'source.xml', 'wb') as out:
            while chunk := src.read(CHUNK):
                if not size and (b'\x00' in chunk[:100]):
                    raise ValueError('仅支持 UTF-8 X4 存档')
                out.write(chunk)
                digest.update(chunk)
                p.Parse(chunk, False)
                size += len(chunk)
                now = time.perf_counter()
                if now - last > .5:
                    progress(f'解析 {size / 1048576:.0f} MiB · {count:,} 个节点 · {now-started:.1f} 秒')
                    last = now
            p.Parse(b'', True)
        if fingerprint(source) != fp:
            raise ValueError('解析过程中源文件发生变化，请重新打开')
        flush()
        db.executemany('INSERT INTO tags VALUES(?,?,?)', [(tid, name, counts[tid]) for name, tid in tags.items()])
        db.commit()
        progress(f'全部 {count:,} 个节点已解析，正在建立查询索引…')
        db.executescript('''CREATE INDEX parent_nodes ON nodes(parent,id);
            CREATE INDEX tag_nodes ON nodes(tag,id);
            CREATE INDEX ref_labels ON labels(ref,node);''')
        db.close()
        db = None
        meta = dict(fingerprint=fp, nodes=count, xml_bytes=size,
                    xml_sha256=digest.hexdigest(), seconds=round(time.perf_counter()-started, 3),
                    tags=len(tags))
        (work / 'meta.tmp').write_text(json.dumps(meta, ensure_ascii=False, indent=2), 'utf-8')
        os.replace(work / 'meta.tmp', work / 'meta.json')
        completed = True
        return str(dest), meta
    finally:
        if db is not None:
            db.close()
        if not completed and work.exists():
            shutil.rmtree(work)


def query(folder, mode='children', value=0, after=0, limit=PAGE):
    limit = max(1, min(int(limit), PAGE))
    with connect(folder) as db:
        base = 'SELECT n.id,t.name,n.parent,n.offset,coalesce(l.ref,\'\'),coalesce(l.label,\'\') FROM nodes n JOIN tags t ON t.id=n.tag LEFT JOIN labels l ON l.node=n.id '
        if mode == 'children':
            where, args = 'n.parent=? AND n.id>?', (int(value), after)
        elif mode == 'tag':
            where, args = 'n.tag=(SELECT id FROM tags WHERE name=?) AND n.id>?', (value, after)
        elif mode == 'id':
            where, args = 'l.ref=? AND n.id>?', (value, after)
        elif mode == 'node':
            where, args = 'n.id=?', (int(value),)
        elif mode == 'text':
            where = 'n.id IN (SELECT node FROM labels WHERE node>? AND instr(lower(label),lower(?))>0 ORDER BY node LIMIT ?)'
            args = (after, value, limit + 1)
        else:
            raise ValueError('未知查询模式')
        return db.execute(base + 'WHERE ' + where + ' ORDER BY n.id LIMIT ?', (*args, limit + 1)).fetchall()


def start_tag(folder, node):
    with connect(folder) as db:
        row = db.execute('SELECT offset FROM nodes WHERE id=?', (int(node),)).fetchone()
    if row is None:
        raise ValueError('节点不存在')
    offset = row[0]
    data = bytearray()
    quote = None
    with open(Path(folder) / 'source.xml', 'rb') as f:
        f.seek(offset)
        while len(data) < 16 * CHUNK:
            chunk = f.read(4096)
            if not chunk:
                break
            for b in chunk:
                data.append(b)
                if quote:
                    if b == quote:
                        quote = None
                elif b in (34, 39):
                    quote = b
                elif b == 62:
                    return offset, bytes(data)
    raise ValueError('起始标签过大或损坏（超过 16 MiB）')


def attributes(raw):
    found = {}
    p = parser()
    p.StartElementHandler = lambda tag, attrs: found.update(attrs)
    tag = raw if raw.rstrip().endswith(b'/>') else raw[:-1] + b'/>'
    p.Parse(tag, True)
    return found


def details(folder, node):
    offset, raw = start_tag(folder, node)
    with open(Path(folder) / 'source.xml', 'rb') as f:
        f.seek(offset)
        preview = f.read(16384).decode('utf-8', errors='replace')
    return attributes(raw), preview


def replaced_tag(raw, edits):
    original = attributes(raw)
    if not edits.keys() <= original.keys():
        raise ValueError('仅允许修改已有属性')
    def sub(m):
        key = m[1].decode('utf-8')
        if key not in edits:
            return m[0]
        value = escape(str(edits[key]), {'"': '&quot;', "'": '&apos;', '\r': '&#13;', '\n': '&#10;', '\t': '&#9;'}).encode('utf-8')
        return m[0][:m.start(3)-m.start()] + value + m[0][m.end(3)-m.start():]
    result = ATTR.sub(sub, raw)
    check = attributes(result)  # Also rejects illegal XML characters.
    for key, value in edits.items():
        if check[key] != str(value):
            raise ValueError('属性回读不一致')
    return result


def validate(path, expected=None, progress=lambda msg: None):
    p = parser()
    count = 0
    checked = set()
    expected = {int(k): v for k, v in (expected or {}).items()}
    def start(tag, attrs):
        nonlocal count
        count += 1
        if count in expected:
            for key, value in expected[count].items():
                if attrs.get(key) != str(value):
                    raise ValueError(f'节点 {count} 的 {key} 回读失败')
            checked.add(count)
    p.StartElementHandler = start
    last = time.perf_counter()
    with input_stream(path) as f:
        while chunk := f.read(CHUNK):
            p.Parse(chunk, False)
            if time.perf_counter() - last > .5:
                progress(f'回读校验：{count:,} 个节点')
                last = time.perf_counter()
        p.Parse(b'', True)
    if checked != set(expected):
        raise ValueError('部分待修改节点未找到')
    return count


def export_save(folder, changes, destination, progress=lambda msg: None):
    """Never overwrites. Publish only after XML and edit read-back validation."""
    folder, dest = Path(folder), Path(destination).resolve()
    if dest.exists():
        raise ValueError('目标已存在。请选择新文件名，原存档不会被覆盖。')
    if not str(dest).lower().endswith(('.xml', '.xml.gz')):
        raise ValueError('目标必须为 .xml 或 .xml.gz')
    meta = json.loads((folder / 'meta.json').read_text('utf-8'))
    patches = []
    for node, edits in changes.items():
        offset, raw = start_tag(folder, int(node))
        patches.append((offset, raw, replaced_tag(raw, edits)))
    patches.sort()
    fd, temporary = tempfile.mkstemp(prefix='.x4-export-', suffix='.tmp', dir=dest.parent)
    os.close(fd)
    try:
        digest = hashlib.sha256()
        done = 0
        last = time.perf_counter()
        with open(folder / 'source.xml', 'rb') as src, open(temporary, 'wb') as base:
            out = gzip.GzipFile(filename='', fileobj=base, mode='wb', compresslevel=1, mtime=0) if str(dest).lower().endswith('.gz') else base
            def copy(n):
                nonlocal done, last
                while n:
                    buf = src.read(min(CHUNK, n))
                    if not buf:
                        raise ValueError('缓存被截断')
                    digest.update(buf)
                    out.write(buf)
                    done += len(buf)
                    n -= len(buf)
                    if time.perf_counter() - last > .5:
                        progress(f'导出 {done / meta["xml_bytes"]:.0%}')
                        last = time.perf_counter()
            for offset, raw, replacement in patches:
                if offset < src.tell():
                    raise ValueError('修改范围重叠')
                copy(offset - src.tell())
                old = src.read(len(raw))
                if old != raw:
                    raise ValueError('缓存已变化')
                digest.update(old)
                done += len(old)
                out.write(replacement)
            copy(meta['xml_bytes'] - src.tell())
            if src.read(1) or digest.hexdigest() != meta['xml_sha256']:
                raise ValueError('缓存校验失败，请重新建立索引')
            if out is not base:
                out.close()
            base.flush()
            os.fsync(base.fileno())
        progress('导出完成，正在完整回读校验…')
        if validate(temporary, changes, progress) != meta['nodes']:
            raise ValueError('导出前后节点数不一致')
        # Hard link provides atomic, no-clobber publication on NTFS.
        os.link(temporary, dest)
        return str(dest)
    finally:
        Path(temporary).unlink(missing_ok=True)
