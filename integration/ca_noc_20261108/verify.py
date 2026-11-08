"""Integrity, source binding and unit checks; no simulator launch."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
CA=ROOT.parents[1]/'snapshots/remote/ca_p0_1b_native_20261103_v11'
INPUTS=('core/common.py','core/native_payload.py','core/coupled_backend.py','core/coaccess.py',
        'core/memory.py','runtime/coupled_backend.cpp','runtime/coupled_matrix.h')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ca-root',type=Path,default=CA)
    ap.add_argument('--freeze',action='store_true')
    args=ap.parse_args()
    files={p.relative_to(ROOT).as_posix():p for p in sorted(ROOT.rglob('*'))
           if p.is_file() and '__pycache__' not in p.parts and p.name!='SOURCE_LOCK.json'}
    for name,p in files.items():
        assert not p.is_symlink() and p.stat().st_size<524288,name
        assert p.suffix not in ('.log','.exe','.so','.o','.zip','.trace','.csv'),name
        if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8-sig'))
        assert not re.search(rb'github_pat_[A-Za-z0-9_]{30,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:OPENSSH |RSA )?PRIVATE KEY-----',p.read_bytes()),name
    current=dict(files={k:sha(v) for k,v in files.items()},ca_inputs={k:sha(args.ca_root/k) for k in INPUTS},
                 source_git_commit='d03b5ea657f191770ae779b62c0708a51482d1a3',
                 ca_snapshot='snapshots/remote/ca_p0_1b_native_20261103_v11',
                 noc_binary_sha256='e6058e940931db3835c4bef6704354aac10851070bc1e0c1f90b65a3f033278a')
    lock=ROOT/'SOURCE_LOCK.json'
    if args.freeze:lock.write_bytes((json.dumps(current,indent=2)+'\n').encode('utf-8'))
    assert json.loads(lock.read_text())==current,'source or evidence differs from locked inputs'
    probe=json.loads((ROOT/'evidence/PROBE_RESULT.json').read_text())
    assert probe['state']=='passed' and probe['consumer']['bitwise_equal']
    assert probe['physical_source_addresses']==[0,4096]
    assert probe['DRAM']['transactions']==probe['DRAM']['callbacks']==3776
    assert probe['DRAM']['packets']==0 and probe['mapping']['changed_bytes']==8192
    for transfer in probe['transfers']:
        assert transfer['issue']<=transfer['receive_complete']<=transfer['drained']<=transfer['write_start']<transfer['consumer_ready']
    cp=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT),'-p','test_*.py','-v'],check=True)
    print(json.dumps(dict(state='passed',release_files=len(files),CA_source_hashes=len(INPUTS),
                          unit_tests=8,actual_joint_probe='passed_limited',performance_ready=False)))

if __name__=='__main__':main()
