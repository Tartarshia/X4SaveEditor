"""Opt-in local benchmark. Exports only into ignored .local, never into save slots."""
import argparse
import ctypes
from ctypes import wintypes
import gzip
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

import core


def peak_memory():
    if os.name != 'nt':
        return None
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [(s, ctypes.c_size_t) for s in ('peak', 'working', 'pagedpeak', 'paged', 'nonpagedpeak', 'nonpaged', 'pagefile', 'peakpagefile')]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL('kernel32')
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL('psapi')
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return counters.peak


def digest(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('save', type=Path)
    ap.add_argument('--fresh', action='store_true', help='Use a separate fresh cache for cold indexing measurement')
    ap.add_argument('--export', action='store_true', help='Validate a one-field edit on a local test copy')
    args = ap.parse_args()
    root = Path(__file__).resolve().parent
    local = root / '.local'
    local.mkdir(exist_ok=True)
    before = digest(args.save)
    cache = root / '.cache'
    if args.fresh:
        cache = local / f'benchmark-{time.time_ns()}'
    start = time.perf_counter()
    folder, meta = core.build_index(args.save, cache, lambda msg: print(msg, flush=True))
    report = {'open_seconds': time.perf_counter()-start, 'nodes': meta['nodes'], 'xml_bytes': meta['xml_bytes'], 'first_index_seconds': meta['seconds']}
    report['cache_bytes'] = sum(p.stat().st_size for p in Path(folder).iterdir())
    report['peak_working_set_after_index'] = peak_memory()
    start = time.perf_counter()
    core.build_index(args.save, cache)
    report['cache_reopen_ms'] = (time.perf_counter()-start)*1000
    cases = [('children', 1), ('tag', 'component'), ('tag', 'account'), ('id', 'player'), ('text', 'not_a_real_macro_benchmark')]
    report['query_ms'] = {}
    for mode, value in cases:
        times = []
        for _ in range(5):
            start = time.perf_counter()
            core.query(folder, mode, value)
            times.append((time.perf_counter()-start)*1000)
        report['query_ms'][f'{mode}:{value}'] = {'median': statistics.median(times), 'max': max(times)}
    if args.export:
        row = core.query(folder, 'tag', 'player')[0]
        node = row[0]
        offset, raw = core.start_tag(folder, node)
        money = core.attributes(raw)['money']
        replacement = str(int(money)+1)
        edits = {node: {'money': replacement}}
        target = local / f'export-check-{time.time_ns()}.xml.gz'
        start = time.perf_counter()
        core.export_save(folder, edits, target, lambda msg: print(msg, flush=True))
        report['export_and_validate_seconds'] = time.perf_counter()-start
        report['export_bytes'] = target.stat().st_size
        # Independent streaming byte comparison against the original compressed save.
        # The fixture edit is in the short header, before the first 1 MiB boundary.
        assert offset + len(raw) < core.CHUNK
        changed_raw = core.replaced_tag(raw, {'money': replacement})
        with core.input_stream(args.save) as original, gzip.open(target, 'rb') as edited:
            first = original.read(core.CHUNK)
            expected = first[:offset] + changed_raw + first[offset+len(raw):]
            assert edited.read(len(expected)) == expected
            while block := original.read(core.CHUNK):
                assert edited.read(len(block)) == block
            assert not edited.read(1)
        report['only_requested_bytes_changed'] = True
        report['export_path'] = str(target)
    report['source_unchanged'] = before == digest(args.save)
    assert report['source_unchanged']
    report['peak_working_set_bytes'] = peak_memory()
    (local / 'benchmark.json').write_text(json.dumps(report, indent=2), 'utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
