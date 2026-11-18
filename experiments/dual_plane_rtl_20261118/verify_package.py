"""Verify published files, tested source identity and archived result receipts."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    manifest=json.loads((R/'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files'].items():
        rel=Path(name);assert not rel.is_absolute() and '..' not in rel.parts
        assert sha(R/rel)==digest,'file hash mismatch: '+name
    e=R/'evidence';build=json.loads((e/'CURRENT_BUILD.json').read_text());matrix=json.loads((e/'MATRIX.json').read_text())
    assert build['status']==matrix['status']=='PASS'
    assert matrix['rtl_digest']==build['source_digest']
    for name,digest in build['source_sha256'].items():assert sha(R/name)==digest,'tested source mismatch: '+name
    control=json.loads((e/'DELAY_CONTROL.json').read_text())
    assert control['status']=='PASS_IDENTICAL_SETUP_AND_HOLD_CONTROL'
    for name,digest in control['source_sha256'].items():assert sha(R/name)==digest,'control source mismatch: '+name
    audit=json.loads((e/'results/AUDIT.json').read_text());assert audit['runs']==len(matrix['tasks'])==312
    assert audit['phase_checks']==1872
    assert sha(e/'results/SUMMARY.csv')==audit['summary_sha256']
    assert sha(e/'results/INTERFERENCE.csv')==audit['interference_sha256']
    for task in matrix['tasks']:
        name=task['case']+'_'+task['arm']+'_b'+str(task['bank'])+('_clk'+str(task['clock']) if task['clock']!=1 else '')
        d=json.loads((e/'results'/(name+'.json')).read_text());assert d['status']=='PASS_RTL_DELIVERY_PAYLOAD_AND_SRAM'
    print('PASS package hashes, exact tested RTL/driver sources, 312 result receipts and summary checksums')
    snapshot=e/'SYNTHESIS_SNAPSHOT.json'
    if snapshot.exists():
        d=json.loads(snapshot.read_text());print('Structural synthesis snapshot:',d['status'],{k:v.get('returncode') for k,v in d.get('variants',{}).items()})
        print('Package verification does not establish synthesis, area or timing sign-off.')
if __name__=='__main__':main()
