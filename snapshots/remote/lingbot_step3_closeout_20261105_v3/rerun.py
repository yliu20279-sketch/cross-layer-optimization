"""One-command isolated replay: python rerun.py NEW_ABSOLUTE_OUTPUT_DIRECTORY."""
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

BASE=Path('/mnt/sda1/h3240101068')
SOURCE=Path(__file__).resolve().parent/'replay_source'
def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    root=Path(sys.argv[1]).resolve()
    if root.parent!=BASE or root.exists():
        raise ValueError('output must be a new direct child of the experiment root')
    # Freeze the final source bytes, including all manual fixes from the prior run.
    source_names=['host.cpp','gateway.cpp','actor.py','completion_gate.py',
                  'cache_evict.h','prepare.py','run.py','phase2.py','audit.py',
                  'receipt_audit_corrected.py','pcie_dma_model.json']
    frozen={n:sha(SOURCE/n) for n in source_names}
    root.mkdir()
    shutil.copy2(Path(__file__).resolve(),root/'rerun.py')
    shutil.copytree(SOURCE,root/'replay_source')
    (root/'SOURCE_BINDING.json').write_text(json.dumps(frozen,indent=2))
    summaries=[]
    for branch in ('cond','uncond'):
        R=root/branch
        R.mkdir()
        for name in source_names:
            assert sha(SOURCE/name)==frozen[name]
            shutil.copy2(SOURCE/name,R/name)
        (R/'data').mkdir()
        # Both feedback passes of this independent run use this CFG only.
        for slot in ('cond','uncond'):
            shutil.copytree(SOURCE/'data'/branch,R/'data'/slot)
        for name in ('prepare.py','run.py'):
            s=(R/name).read_text().replace('B=R.parent;',f'B=pathlib.Path({str(BASE)!r});')
            (R/name).write_text(s)
        s=(R/'actor.py').read_text().replace("branch='cond' if roundno==1 else 'uncond'",f"branch={branch!r}")
        (R/'actor.py').write_text(s)
        for name in ('audit.py','receipt_audit_corrected.py'):
            s=(R/name).read_text().replace("[(1,'cond'),(2,'uncond')]",repr([(1,branch),(2,branch)]))
            s=s.replace('two CFG paths use service round slots; uncond consumes preceding same-shape PopNet delay profile',
                        'both service rounds use the same CFG; round2 consumes its own round1 profile')
            (R/name).write_text(s)
        env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
        with (R/'launcher.log').open('w') as log:
            subprocess.run([sys.executable,str(R/'run.py')],stdout=log,stderr=subprocess.STDOUT,
                           env=env,check=True,timeout=750)
        subprocess.run([sys.executable,str(R/'receipt_audit_corrected.py')],check=True,timeout=60)
        receipts=[]
        for k in (1,2):
            rows=list(csv.DictReader((R/'run'/f'noc_feedback_round{k}.csv').open()))
            assert rows and all(int(x['profile_applied'])==k-1 for x in rows)
            for name in ('K_F32.bin','K_BF16.bin'):
                assert (R/'case1/N00'/name).read_bytes()==(R/'case2/N00'/name).read_bytes()
            gate=json.loads((R/f'case{k}/N00/GATE.json').read_text())
            assert gate['identity']['cfg']==branch
            receipts.append(dict(pass_number=k,feedback_rows=len(rows),
                                 feedback_applied=k==2,
                                 input_sha256=sha(R/'data'/branch/'K_x.bin'),
                                 bench_sha256=sha(R/f'case{k}/bench.txt'),
                                 delay_sha256=sha(R/f'case{k}/delayInfo.txt'),
                                 feedback_sha256=sha(R/'run'/f'noc_feedback_round{k}.csv'),
                                 gate=gate))
        summaries.append(dict(branch=branch,passes=receipts,
                              numeric_and_runtime_receipt_audit=sha(R/'RUNTIME_RECEIPT_AUDIT.json')))
    result=dict(state='PASS_LIMITED_INDEPENDENT_CFG_FEEDBACK_REPLAY',branches=summaries,
                same_branch_first_pass_profile_second_pass_consumption=True,
                limits=['single K projection per CFG, two feedback passes',
                        'parameterized PCIe serialized queue0 model',
                        'CPU and writeback times conservatively observed at receiver',
                        'no feedback convergence or full-layer-cost claim'])
    (root/'CLOSEOUT_AUDIT.json').write_text(json.dumps(result,indent=2))
    members=[p for p in sorted(root.rglob('*')) if p.is_file()
             and p.suffix!='.gz' and '__pycache__' not in p.parts and p.stat().st_size<16*2**20]
    manifest=[dict(file=str(p.relative_to(root)),bytes=p.stat().st_size,sha256=sha(p)) for p in members]
    (root/'MANIFEST.json').write_text(json.dumps(manifest,indent=2))
    with tarfile.open(root/'closeout_review.tar.gz','w:gz') as t:
        for p in members+[root/'MANIFEST.json']:
            t.add(p,arcname=str(p.relative_to(root)))
    (root/'DELIVERY.json').write_text(json.dumps(dict(sha256=sha(root/'closeout_review.tar.gz'),
                    bytes=(root/'closeout_review.tar.gz').stat().st_size,payloads=len(members)),indent=2))
    print(json.dumps(result))
if __name__=='__main__':
    main()
