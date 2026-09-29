"""Read-only semantic navigation over the existing complete node index."""
from functools import lru_cache
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

import core

VERSION = 1
CATALOG = [
    ('money', '玩家资金', '玩家', '玩家阵营账户、同 ID 账户及金额摘要；不包含无关空间站账户。多处记录可能需要一致，入口不会自动同步。'),
    ('player', '玩家角色', '玩家', 'class=player 的角色节点；可继续查看位置、装备与其他子节点。'),
    ('inventory', '个人背包', '玩家', '玩家角色 inventory 下的条目；与 NPC 背包、舰船货仓分开。'),
    ('blueprints', '已有蓝图', '玩家', '玩家角色 blueprints 下已保存的蓝图；新增蓝图请使用“解锁蓝图”功能面板。'),
    ('research', '科研记录', '玩家', '玩家角色 research 下的记录；可能只有已开始或完成的项目，不代表完整科技树。'),
    ('reputation', '玩家相关声望', '阵营', '玩家阵营对外关系，以及其他阵营对玩家的 relation / booster；方向与临时加成分开显示。'),
    ('licences', '玩家许可证', '阵营', '玩家阵营 licences 条目；仪式、剧情和声望还可能有其他条件。'),
    ('ships', '玩家舰船', '资产', '明确标记 owner=player 的 ship_* 组件；显示原始名称、macro 与识别码。'),
    ('stations', '玩家空间站', '资产', '明确标记 owner=player 的 station 组件。'),
    ('buildstorage', '建造仓储', '资产', '明确标记 owner=player 的 buildstorage 组件；进入子节点查看建造物资。'),
    ('skills', '船员 / 人员技能', '资产', '归属玩家的 NPC 或舰船 / 空间站下的 skills；具名人员和匿名船员都可能存在。'),
    ('cargo', '货仓 / 弹药', '资产', '归属玩家的 cargo 与 ammunition 容器；双击继续查看物资条目及数量，容量仍需自行核对。'),
    ('modifications', '舰船 / 装备改装', '资产', '归属玩家的 modification 容器；双击展开改装项目。'),
    ('discovery', '地图 / 百科记录', '其他', '玩家角色 known、discovered、unlocks 等容器；用于查看已有记录，不自动揭示地图。'),
    ('missions', '任务记录', '其他', '存档顶层 missions 的直接子节点。任务还依赖 MD 状态，入口只负责定位。'),
]
KEYS = {row[0] for row in CATALOG}
TITLES = {row[0]: row[1] for row in CATALOG}


def ensure_index(folder, progress=lambda msg: None):
    folder = Path(folder)
    dest = folder / f'shortcuts-v{VERSION}.db'
    signature = json.loads((folder / 'meta.json').read_text('utf-8'))['xml_sha256']
    if dest.exists():
        with closing(sqlite3.connect(dest)) as check:
            if check.execute('SELECT value FROM meta WHERE key=?', ('source',)).fetchone() == (signature,):
                return dest
    fd, name = tempfile.mkstemp(prefix='shortcuts-', suffix='.tmp', dir=folder)
    os.close(fd)
    out = sqlite3.connect(name)
    started = time.perf_counter()
    try:
        out.executescript('''CREATE TABLE members(category TEXT,node INTEGER,context TEXT,
            PRIMARY KEY(category,node)) WITHOUT ROWID;
            CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);''')
        with core.connect(folder) as db, (folder / 'source.xml').open('rb') as xml:
            tags = dict(db.execute('SELECT name,id FROM tags'))
            tag_names = {v:k for k,v in tags.items()}
            @lru_cache(maxsize=50000)
            def node_info(node):
                return db.execute('SELECT parent,tag,offset FROM nodes WHERE id=?', (node,)).fetchone()
            def attrs(node):
                return core.attributes(core.read_start_tag(xml, node_info(node)[2]))
            def children(parent, tag=None):
                if tag:
                    return [r[0] for r in db.execute('SELECT id FROM nodes WHERE parent=? AND tag=? ORDER BY id', (parent,tags.get(tag,-1)))]
                return [(r[0],tag_names[r[1]]) for r in db.execute('SELECT id,tag FROM nodes WHERE parent=? ORDER BY id', (parent,))]
            def add(category, node, context):
                out.execute('INSERT OR IGNORE INTO members VALUES(?,?,?)', (category,node,context))
            def add_children(category, parent, context):
                for node, tag in children(parent):
                    add(category,node,context)
            @lru_cache(maxsize=50000)
            def owner(node):
                # Iterative ascent keeps arbitrary save depth out of Python recursion.
                current = node
                while current:
                    parent, tag, offset = node_info(current)
                    if tag == tags.get('component'):
                        data = attrs(current)
                        if 'owner' in data:
                            label = data.get('name') or data.get('code') or data.get('macro') or data.get('class','component')
                            return data['owner'], f'{data.get("class","component")} {label[:120]} · #{current}'
                    current = parent
                return '', ''
            progress('定位玩家角色、账户和阵营…')
            roots = children(0, 'savegame')
            if not roots:
                raise ValueError('未找到 savegame 根节点')
            root = roots[0]
            for info in children(root,'info'):
                for node in children(info,'player'):
                    if 'money' in attrs(node):
                        add('money',node,'玩家摘要 / info/player@money')
            for stats in children(root,'stats'):
                for node in children(stats,'stat'):
                    if attrs(node).get('id') == 'money_player':
                        add('money',node,'玩家金额统计 / stats/stat@value')
            account_ids = set()
            for universe in children(root,'universe'):
                for factions in children(universe,'factions'):
                    for faction in children(factions,'faction'):
                        faction_id = attrs(faction).get('id','')
                        if faction_id == 'player':
                            for account in children(faction,'account'):
                                add('money',account,'玩家阵营主账户 / account@amount')
                                account_id = attrs(account).get('id')
                                if account_id:
                                    account_ids.add(account_id)
                            for licences in children(faction,'licences'):
                                add_children('licences',licences,'玩家许可证')
                        for relations in children(faction,'relations'):
                            for rel, tag in children(relations):
                                if tag not in ('relation','booster'):
                                    continue
                                target = attrs(rel).get('faction')
                                if faction_id == 'player' or target == 'player':
                                    add('reputation',rel,f'{faction_id} → {target or "?"}' + (' · 临时 booster' if tag=='booster' else ' · relation'))
            for ref in account_ids:
                for node, in db.execute('SELECT n.id FROM labels l JOIN nodes n ON n.id=l.node WHERE l.ref=? AND n.tag=?', (ref,tags.get('account',-1))):
                    add('money',node,'与玩家主账户共享 ID / '+ref)
            candidates = db.execute("SELECT n.id FROM nodes n JOIN labels l ON l.node=n.id WHERE n.tag=? AND (l.label LIKE '%owner=player%' OR l.label LIKE '%class=player%') ORDER BY n.id", (tags.get('component',-1),)).fetchall()
            for node, in candidates:
                data = attrs(node)
                cls = data.get('class','')
                if cls == 'player':
                    add('player',node,'玩家角色 / class=player')
                    for child, tag in children(node):
                        if tag in ('inventory','blueprints','research'):
                            add_children(tag,child,f'玩家角色 / {tag} · #{node}')
                        elif tag in ('known','discovered','unlocks'):
                            add('discovery',child,'玩家角色 / '+tag)
                if data.get('owner') != 'player':
                    continue
                category = 'ships' if cls.startswith('ship_') else {'station':'stations','buildstorage':'buildstorage'}.get(cls)
                if category:
                    add(category,node,'识别码 '+data.get('code','—'))
            for missions in children(root,'missions'):
                add_children('missions',missions,'任务 / missions')
            # Only scan indexed tags, not all XML nodes. Never use label substrings
            # as the final ownership decision: read actual component attributes.
            for category, names in [('skills',('skills',)),('cargo',('cargo','ammunition')),('modifications',('modification',))]:
                scanned = 0
                last = 0
                for tag in names:
                    for node, parent in db.execute('SELECT id,parent FROM nodes WHERE tag=? ORDER BY id', (tags.get(tag,-1),)):
                        owned, context = owner(parent)
                        if owned == 'player':
                            add(category,node,context)
                        scanned += 1
                        if time.perf_counter()-last > .5:
                            progress(f'定位常用节点：{TITLES[category]} · 已检查 {scanned:,} 项 · {time.perf_counter()-started:.1f} 秒')
                            last = time.perf_counter()
        out.execute('INSERT INTO meta VALUES(?,?)', ('source',signature))
        out.execute('INSERT INTO meta VALUES(?,?)', ('seconds',str(time.perf_counter()-started)))
        out.commit()
        out.close()
        os.replace(name,dest)
        return dest
    finally:
        out.close()
        Path(name).unlink(missing_ok=True)


def catalog(folder, progress=lambda msg: None):
    path = ensure_index(folder, progress)
    db = sqlite3.connect(path)
    try:
        counts = dict(db.execute('SELECT category,count(*) FROM members GROUP BY category'))
        return [dict(key=key,title=title,group=group,description=description,count=counts.get(key,0)) for key,title,group,description in CATALOG]
    finally:
        db.close()


def query(folder, category, after=0, progress=lambda msg: None):
    if category not in KEYS:
        raise ValueError('未知快捷入口')
    path = ensure_index(folder,progress)
    with core.connect(folder) as db:
        db.execute('ATTACH DATABASE ? AS quick', (path.resolve().as_uri()+'?mode=ro',))
        return db.execute('''SELECT n.id,t.name,n.parent,n.offset,coalesce(l.ref,''),
            trim(coalesce(l.label,'') || ' · ' || q.context,' ·')
            FROM quick.members q JOIN nodes n ON n.id=q.node JOIN tags t ON t.id=n.tag
            LEFT JOIN labels l ON l.node=n.id
            WHERE q.category=? AND q.node>? ORDER BY q.node LIMIT ?''', (category,int(after),core.PAGE+1)).fetchall()
