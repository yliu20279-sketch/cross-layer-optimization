"""Read-only release audit by default; never import or run snapshot scripts."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {'__pycache__', '.git'}
SECRET = re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}')
FORBIDDEN = {'.zip', '.gz', '.exe', '.dll', '.so', '.a', '.vvp', '.pt', '.pth', '.safetensors', '.npy', '.npz', '.bin', '.log', '.trace', '.csv'}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def sources():
    return {p.relative_to(ROOT).as_posix(): p for p in sorted(ROOT.rglob('*'))
            if p.is_file() and not any(part in IGNORED for part in p.relative_to(ROOT).parts)
            and p.name != 'SOURCE_MANIFEST.json'}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--write-manifest', action='store_true', help='maintainer: freeze current release bytes')
    args = ap.parse_args()
    files = sources()
    for name, path in files.items():
        assert not path.is_symlink(), name
        assert path.stat().st_size <= 1_048_576, name
        assert path.suffix.lower() not in FORBIDDEN, 'unexpected artifact: '+name
        assert not SECRET.search(path.read_bytes()), 'credential pattern: '+name
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=name)
        elif path.suffix == '.json':
            json.loads(path.read_text(encoding='utf-8-sig'))
    current = {name: dict(bytes=p.stat().st_size, sha256=digest(p)) for name, p in files.items()}
    frozen = ROOT/'SOURCE_MANIFEST.json'
    if args.write_manifest:
        frozen.write_text(json.dumps(dict(schema=1, files=current), indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    assert json.loads(frozen.read_text(encoding='utf-8'))['files'] == current, 'release files changed'
    origin_checks = 0
    for manifest in ('REMOTE_SOURCE_MANIFEST.json', 'LOCAL_SOURCE_MANIFEST.json'):
        for row in json.loads((ROOT/manifest).read_text(encoding='utf-8'))['files']:
            if 'sha256' in row:
                assert digest(ROOT/row['path']) == row['sha256'], row['path']
                origin_checks += 1
            if 'patch_sha256' in row:
                assert digest(ROOT/row['patch']) == row['patch_sha256'], row['patch']
                origin_checks += 1
    acceptance = json.loads((ROOT/'evidence/noc_short_validation_20261108/FAST_CORRECTNESS_ACCEPTANCE.json').read_text())
    assert acceptance['state'] == 'passed'
    checked = 0
    for proof in acceptance['proofs'].values():
        suffix = proof['path'].split('/h4567/', 1)[1]
        receipt = ROOT/'evidence'/suffix
        assert receipt.is_file(), 'missing receipt: '+suffix
        assert digest(receipt) == proof['sha256'], 'receipt mismatch: '+suffix
        checked += 1
    assert checked == 8
    print(json.dumps(dict(state='passed', files=len(files), original_source_or_patch_hashes=origin_checks,
                          linked_acceptance_receipts=checked, source_bytes=sum(p.stat().st_size for p in files.values()),
                          scope='archive integrity, syntax and receipt linkage; not a simulator rerun')))

if __name__ == '__main__':
    main()
