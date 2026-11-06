from pathlib import Path
import time,json,traceback
R=Path(__file__).resolve().parent;deadline=time.monotonic()+135000
try:
 while not (R/'RUN_EXIT.json').exists():
  if time.monotonic()>deadline:raise TimeoutError('cost run wait')
  time.sleep(20)
 result=json.loads((R/'RUN_EXIT.json').read_text());assert result['returncode']==0 and result['reason'] is None,result
 rounds=[]
 for case in ['case1','case2']:
  D=R/case
  rows=[json.loads(x) for x in (D/'CPU_EXCLUSIVE_SERVICE_CLOCK.jsonl').read_text().splitlines()]
  original=[json.loads(x) for x in (D/'CPU_SERVICE_COMPLETIONS.jsonl').read_text().splitlines()]
  assert len(rows)==len(original)>0
  for i,(a,z) in enumerate(zip(rows,original),1):
   assert a['sequence']==i and all(a[k]==z[k] for k in ['kind','input_bytes','output_bytes'])
   assert 0<a['start_fs']<=a['end_fs']
   if i>1:assert rows[i-2]['end_fs']<=a['start_fs']
  kinds={}
  for x in rows:
   v=kinds.setdefault(str(x['kind']),{'calls':0,'elapsed_fs':0});v['calls']+=1;v['elapsed_fs']+=x['end_fs']-x['start_fs']
  rounds.append({'case':case,'calls':len(rows),'kinds':kinds,'sum_service_elapsed_fs':sum(x['end_fs']-x['start_fs'] for x in rows)})
 (R/'CPU_SERVICE_COST_AUDIT.json').write_text(json.dumps({'state':'PASS_LIMITED_TWO_LAYER_CPU_SERVICE_INTERNAL_CLOCK','rounds':rounds,'unit':'femtoseconds','includes_memory_stalls_and_observer_boundary_cost':True,'excludes_RPC_transfer_and_buffer_setup':True,'not_to_add_again_to_RPC_envelope':True,'startup_and_nonservice_CPU_control_exclusive':False,'critical_path_closed':False,'full_target_timing':False},indent=2))
except Exception:
 (R/'CPU_SERVICE_COST_FAILURE.txt').write_text(traceback.format_exc());raise
