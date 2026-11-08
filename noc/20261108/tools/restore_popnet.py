"""Restore accepted adapters onto a legally held exact upstream tree."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'snapshots/noc_crosslayer_validation_20261108/noc/adapter/'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--upstream', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    source, dest = args.upstream.resolve(), args.out.resolve()
    if not source.is_dir() or dest.exists() or source in dest.parents or dest in source.parents:
        ap.error('use an existing authorized upstream and a separate, non-existing output directory')
    patch = shutil.which('patch')
    if not patch:
        ap.error('system patch command is required')
    manifest = json.loads((ROOT/'REMOTE_SOURCE_MANIFEST.json').read_text())
    rows = [r for r in manifest['files'] if r['path'].startswith(PREFIX)]
    for row in rows:
        rel = row['path'][len(PREFIX):]
        if 'baseline_sha256' in row:
            assert sha(source/rel) == row['baseline_sha256'], 'baseline mismatch: '+rel
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns('build', 'build_*', '.git', '__pycache__'))
    for row in rows:
        rel = row['path'][len(PREFIX):]
        if 'patch' in row:
            assert sha(ROOT/row['patch']) == row['patch_sha256']
            subprocess.run([patch, '--batch', '--fuzz=0', '-p1', '-i', str(ROOT/row['patch'])],
                           cwd=dest, check=True, timeout=30)
        elif row['kind'] == 'project_added_source':
            (dest/rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/row['path'], dest/rel)
        expected = row.get('accepted_sha256', row.get('sha256'))
        assert sha(dest/rel) == expected, 'restored file mismatch: '+rel
    print(json.dumps(dict(state='passed', files_checked=len(rows),
                          scope='accepted adapter source restoration; not rebuild or runtime validation')))

if __name__ == '__main__':
    main()
