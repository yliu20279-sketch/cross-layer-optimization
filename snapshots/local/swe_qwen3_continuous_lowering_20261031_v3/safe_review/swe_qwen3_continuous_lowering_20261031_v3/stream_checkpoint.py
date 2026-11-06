import json,hashlib,tarfile,datetime,shutil
from pathlib import Path
R=Path(__file__).resolve().parent;BASE=R.parent/'swe_qwen3_continuous_lowering_20261031_v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
freeze=json.loads((R/'FREEZE.json').read_text())
for n,h in freeze.items():assert sha(R/n)==h
snap=R/'checkpoint_native';snap.mkdir(exist_ok=False)
for n in ['IMMEDIATE_FP32_GATES.jsonl','LOWERING.jsonl','npusim_dram_transactions_0_0.csv','IO_SRAM_GATES.csv']:
 p=R/'case1'/n
 if p.exists():(snap/n).write_bytes(p.read_bytes())
gates=[json.loads(s) for s in (snap/'IMMEDIATE_FP32_GATES.jsonl').read_text().splitlines() if s.endswith('}')];assert gates and all(v['exact'] for v in gates)
status=dict(state='RUNNING_WITH_STRICT_FP32_PREFIX_PASS',checked_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),matrices_exact=len(gates),FP32_elements_exact=sum(v['M']*v['N'] for v in gates),first_shape=[gates[0][v] for v in ['M','N','K']],host_GiB=128,HB_GiB=8,max_packet_bytes=65536,full_layers_passed=False,full_steps_1_7=False);(R/'CHECKPOINT_STATUS.json').write_text(json.dumps(status,indent=2))
shutil.copy2(BASE/'build_math.py',R/'build_math.py')
names=set(freeze)|{'FREEZE.json','LAUNCH_PID.json','RUN_PID.json','SUPPLEMENTAL_STRICT_GATE.json','CHECKPOINT_STATUS.json','preflight.py','audit_raw_when_ready.py','safe_collect.py','build_math.py'}
names|={'oracle_cpu/'+p.name for p in (R/'oracle_cpu').iterdir() if p.is_file() and p.suffix in ['.json','.bin']}
names|={str(p.relative_to(R)) for p in snap.iterdir()}
members=sorted(R/n for n in names if (R/n).is_file());manifest=[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=sha(p)) for p in members];(R/'CHECKPOINT_MANIFEST.json').write_text(json.dumps(manifest,indent=2));pack=R.parent/(R.name+'_CHECKPOINT_REVIEW.tar.gz')
with tarfile.open(pack,'w:gz',dereference=True) as t:
 for p in members+[R/'CHECKPOINT_MANIFEST.json']:t.add(p,arcname=R.name+'/'+str(p.relative_to(R)))
out=dict(state='RUNNING_STRICT_PREFIX_REVIEW_NOT_COMPLETE',members=len(members),archive=str(pack),bytes=pack.stat().st_size,sha256=sha(pack),snapshot=status,full_steps_1_7=False);(R/'CHECKPOINT_DELIVERY.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
