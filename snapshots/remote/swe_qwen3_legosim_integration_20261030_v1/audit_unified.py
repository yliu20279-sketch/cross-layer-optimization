"""Independent stdlib check of integrated fragment, NOT whole model acceptance."""
import csv,hashlib,json,re
from pathlib import Path
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def logcheck(log,run,count):
 text=log.read_text();statuses=[int(v) for v in re.findall(r'terminate with status = (\d+)',text)]
 delay=run/'delayInfo.txt';rows=delay.read_text().splitlines() if delay.is_file() else []
 return bool(statuses) and all(v==0 for v in statuses) and len(rows)==count
assert logcheck(R/'smoke/RUN_V5.log',R/'smoke/attempt5',2)
for log,run in [('RUN_V2.log','attempt2'),('RUN_V3.log','attempt3'),('RUN_V4.log','attempt4')]:assert not logcheck(R/'smoke'/log,R/'smoke'/run,2)
assert json.loads((R/'memory_smoke/attempt1/ROUNDTRIP.json').read_text())['finite_values']==65280
assert logcheck(R/'memory_smoke/RUN.log',R/'memory_smoke/attempt1',161)
ref=R.parent/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1';fs=json.loads((ref/'FILES.json').read_text());checked=[]
for directory,log,expected_rounds in [('real_front','real_front/RUN.log',1),('real_front/attempt2_feedback/payload','real_front/RUN_FEEDBACK.log',2),('real_front/attempt3_guarded/payload','real_front/RUN_GUARDED.log',2)]:
 root=R/directory;state=json.loads((root/'CPU_PASS.json').read_text());assert state['state']=='PASS_UNIFIED_REAL_PREFILL_DECODE_RESIDUAL_NORM'
 for phase in ['prefill','decode']:
  v=next(v for v in fs if v['phase']==phase and v['layer']==0 and v['stage']=='post_attention_norm');p=root/(phase+'_ACTUAL.bin');assert p.read_bytes()==(ref/v['path']).read_bytes();checked.append(dict(path=str(p.relative_to(R)),elements=p.stat().st_size//2,sha256=sha(p)))
 rows=list(csv.DictReader((root/'schedule.csv').open()));assert len(rows)==6
 for phase in ['0','1']:
  rr=[v for v in rows if v['phase']==phase];assert [v['id'] for v in rr]==['1','2','3']
  for v in rr:assert int(v['ready'])<=int(v['start'])<=int(v['complete'])
  assert int(rr[0]['complete'])<=int(rr[1]['start']) and int(rr[1]['complete'])<=int(rr[2]['start'])
 run=R/'real_front'/('attempt1' if expected_rounds==1 else 'attempt2_feedback' if 'FEEDBACK' in log else 'attempt3_guarded')
 assert logcheck(R/log,run,315)
 if expected_rounds==2:assert 'Load 315 delay records' in (R/log).read_text()
negative=json.loads((R/'entry_guarded/NEGATIVE_RESULTS.json').read_text());assert len(negative)==3 and all(v['expected_exit']==v['actual_exit'] for v in negative)
fresh=json.loads((R/'entry_guarded/FRESH_DELAY_NEGATIVE.json').read_text());assert fresh['actual_exit']==4 and fresh['stale_file_rejected']
profile=json.loads((R/'V3_6_HOST128_HB8_BINDING.json').read_text());assert profile['NPU_count']*profile['HB_per_NPU_bytes']==profile['total_HB_bytes']==8*2**30
out=dict(state='PASS_LIMITED_UNIFIED_FRAGMENT_AUDIT',numeric_outputs=checked,phase_failure_negative_controls=4,false_success_negative_controls=3,real_front_Sniper_ROIs=5,real_front_NPU_program_process_runs=5,full_unified_layers=0,full_unified_KV=False,full_target_timing='NOT_CERTIFIED',active_HB_bytes=512*2**20,architectural_HB_bytes=8*2**30,scope='last output files retained per multi-round case; each round CPU assertion passed by process exit, not independent per-round raw output replay')
(R/'INDEPENDENT_UNIFIED_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
