import json,hashlib,tarfile,datetime
from pathlib import Path
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
freeze=json.loads((R/'FREEZE.json').read_text())
for n,h in freeze.items():assert sha(R/n)==h
root_completed=0
if (R/'case1/LOWERING.jsonl').exists():root_completed=sum(1 for v in (R/'case1/LOWERING.jsonl').read_text().splitlines() if v.endswith('}'))
snapshot=dict(state='RUNNING_NOT_COMPLETE',checked_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),case1_root_matrices_completed=root_completed,full_layers_passed=False,CPU_oracle_calls=759,CPU_oracle_is_target_execution=False,host_GiB=128,HB_GiB=8,math_table_bytes=17179869184+131072,weight_bytes=61066575648,full_steps_1_7=False)
(R/'CHECKPOINT_STATUS.json').write_text(json.dumps(snapshot,indent=2))
names=set(freeze)|{'FREEZE.json','CPU_BUILD_COMMAND.json','CPU_VECTORIZATION.log','CPU_CONTROLS_ISA.json','CANDIDATE_READY.json','LAUNCH_PID.json','RUN_PID.json','SAFE_COLLECTOR_PID.json','SUPPLEMENTAL_STRICT_GATE.json','CHECKPOINT_STATUS.json','preflight.py','audit_raw_when_ready.py','safe_collect.py'}
names|={'oracle_cpu/'+p.name for p in (R/'oracle_cpu').iterdir() if p.is_file() and p.suffix in ['.json','.bin']}
members=sorted(R/n for n in names if (R/n).is_file());manifest=[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=sha(p)) for p in members]
(R/'CHECKPOINT_MANIFEST.json').write_text(json.dumps(manifest,indent=2));pack=R.parent/(R.name+'_CHECKPOINT_REVIEW.tar.gz')
with tarfile.open(pack,'w:gz',dereference=True) as t:
 for p in members+[R/'CHECKPOINT_MANIFEST.json']:t.add(p,arcname=R.name+'/'+str(p.relative_to(R)))
receipt=dict(state='RUNNING_REVIEW_READY_NOT_FUNCTIONAL_PASS',archive=str(pack),bytes=pack.stat().st_size,sha256=sha(pack),members=len(members),large_math_data_left_on113=True,full_steps_1_7=False)
(R/'CHECKPOINT_DELIVERY.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
