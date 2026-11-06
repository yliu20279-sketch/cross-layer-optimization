"""Compact source/evidence delivery; large original event logs stay on 113."""
from pathlib import Path
import hashlib
import io
import json
import subprocess
import tarfile
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):h.update(block)
    return h.hexdigest()
build=json.loads((ROOT/'evidence/COUPLED_BUILD_04.json').read_text())
assert sha(build['binary'])==build['sha256']
ldd=subprocess.check_output(['ldd',build['binary']],text=True)
assert 'not found' not in ldd
libraries=[]
for line in ldd.splitlines():
    part=line.split('=>',1)[-1].strip().split()
    if part and part[0].startswith('/'):
        p=Path(part[0]);libraries.append({'path':str(p),'resolved':str(p.resolve()),'bytes':p.stat().st_size,'sha256':sha(p)})
runtime={'binary':build['binary'],'binary_sha256':build['sha256'],'libraries':libraries,'ldd':ldd,
         'scope':'actual serial coupled candidate, not parallel/performance admission'}
(ROOT/'evidence/RUNTIME_IDENTITY_V5.json').write_text(json.dumps(runtime,indent=2))
roots=[ROOT/'evidence']+[ROOT/'runs'/('%s_%s'%(model,tag)) for model in ('qwen3','qwen15') for tag in ('layer01','layer02')]
roots += [ROOT/name for name in ('coupled_probe_01','coupled_probe_02','startup_debug_01','precision_contract_probe01',
    'physical_permutation_probe01','cross_object_pp_probe01')]+[ROOT/('physical_permutation_negative_%d'%i) for i in range(4)]
for number in range(1,5):
    directory=ROOT/('build_%02d'%number)
    if directory.is_dir():roots.append(directory)
selected=[];remote_only=[]
for directory in roots:
    if not directory.is_dir():continue
    for p in directory.rglob('*'):
        if not p.is_file() or '__pycache__' in p.parts:continue
        rel=p.relative_to(ROOT).as_posix()
        if p.suffix in ('.o','.so') or p.name=='coupled_backend' or p.name=='core' or p.name.startswith('core.'):
            remote_only.append({'path':str(p),'bytes':p.stat().st_size,'reason':'binary/object/core retained remotely'});continue
        if p.name=='LIVE_EVENTS.csv' and p.stat().st_size>16*1024**2:
            audit=p.parent.parent/'INDEPENDENT_RAW_AUDIT.json'
            if audit.is_file():
                proof=json.loads(audit.read_text());assert proof['raw_event_bytes']==p.stat().st_size
                remote_only.append({'path':str(p),'bytes':p.stat().st_size,'sha256':proof['raw_event_sha256'],
                                    'audit':str(audit),'reason':'large raw log fully streaming-audited; not downloaded'})
            else:raise AssertionError(('large log missing independent audit',str(p)))
            continue
        assert p.stat().st_size<=32*1024**2,('unexpected compact member size',str(p))
        selected.append(p)
selected=sorted(set(selected))
records=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in selected]
index={'scope':'compact review only; all raw original logs retained remotely','files':records,'remote_only':remote_only,
       'full_checkpoint_weights_downloaded':False,'formal_performance_runs':0}
with tarfile.open(ROOT/'COMPACT_REVIEW_V5.tar.gz','w:gz') as tar:
    for p in selected:tar.add(p,arcname=p.relative_to(ROOT).as_posix(),recursive=False)
    payload=json.dumps(index,indent=2).encode();info=tarfile.TarInfo('REVIEW_MEMBER_INDEX.json');info.size=len(payload)
    tar.addfile(info,io.BytesIO(payload))
print(json.dumps({'members':len(records),'remote_large_logs':sum(x.get('sha256') is not None for x in remote_only),
                  'compact_bytes':(ROOT/'COMPACT_REVIEW_V5.tar.gz').stat().st_size,'runtime_libraries':len(libraries)}))
