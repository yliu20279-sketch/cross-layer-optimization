"""Idle-priority read-only checkpoint hashing; no weights interpreted/loaded."""
from pathlib import Path
import hashlib
import json
import time
import sys

root = Path('/mnt/sda1/models/Qwen3-30B-A3B-modelscope')
start = time.monotonic()
records = []
files = sorted(root.glob('*.safetensors'))
for p in files:
    h = hashlib.sha256()
    with p.open('rb') as handle:
        for block in iter(lambda: handle.read(4 * 1024**2), b''):
            h.update(block)
            if time.monotonic() - start > 600:
                print(json.dumps({'status': 'PARTIAL_DEADLINE', 'files': records,
                                  'unfinished': str(p), 'model_runs': 0}))
                raise SystemExit(0)
    row = {'path': str(p), 'bytes': p.stat().st_size, 'sha256': h.hexdigest()}
    records.append(row)
    print('HASHED %d/%d %s' % (len(records), len(files), p.name), file=sys.stderr, flush=True)
print(json.dumps({'status': 'COMPLETE_READONLY_SHA256', 'files': records,
                  'elapsed_seconds': time.monotonic() - start, 'model_runs': 0}))
