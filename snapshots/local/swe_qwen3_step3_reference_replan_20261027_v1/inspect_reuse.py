"""Read existing completed requests only; CPU, no model, no task issue/gold access."""
import hashlib,json,sys
from pathlib import Path
import torch
torch.set_num_threads(1)
BASE=Path('/mnt/sda1/h3240101068')
OUT=Path(__file__).resolve().parent
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8*1024*1024):h.update(b)
 return h.hexdigest()
def schema(v):
 if torch.is_tensor(v):return dict(shape=list(v.shape),dtype=str(v.dtype),finite=bool(torch.isfinite(v).all()) if v.is_floating_point() else True)
 if isinstance(v,dict):return {k:schema(x) for k,x in v.items() if k!='input_token_ids'}
 if isinstance(v,(tuple,list)):return [schema(x) for x in v]
 return v
rows=[]
for name,rid in [('swe_qwen3_step3_gpu_20261026_v1','R0002'),('swe_qwen3_step3_development_20261026_v6','R0001'),('swe_qwen3_step3_holdout_20261026_v1','R0001')]:
 root=BASE/name;p=root/'requests'/rid
 req=json.loads((p/'REQUEST.json').read_text());manifest=json.loads((p/'MANIFEST.json').read_text())
 checks=[]
 for item in manifest:
  # Do not read messages/problem statements or evaluator payloads.
  if item['path'] not in ['REQUEST.json','actual_routes.pt','layer0_actual_fixtures.pt']:continue
  q=p/item['path'];checks.append(dict(path=item['path'],bytes=q.stat().st_size,sha256=sha(q),matches=q.stat().st_size==item['bytes'] and sha(q)==item['sha256']))
 fixtures=torch.load(p/'layer0_actual_fixtures.pt',map_location='cpu',weights_only=True)
 routes=torch.load(p/'actual_routes.pt',map_location='cpu',weights_only=True)
 replay=[]
 phases=[]
 for phase,f in fixtures.items():
  if phase=='prefill_chunks':phases.extend((phase+'/'+k,v) for k,v in f.items())
  else:phases.append((phase,f))
 for phase,f in phases:
  if 'router_logits' not in f:continue
  prob=torch.softmax(f['router_logits'],dim=-1,dtype=torch.float32)
  val,ids=torch.topk(prob,8,dim=-1);weights=(val/val.sum(-1,keepdim=True)).to(torch.bfloat16)
  actual=f['actual_selected_experts'];different=(ids!=actual).any(-1)
  tied=[]
  for row in torch.where(different)[0].tolist():
   tied.append(dict(token=row,cpu_ids=ids[row].tolist(),gpu_ids=actual[row].tolist(),
    cpu_selected_logits=f['router_logits'][row,ids[row]].float().tolist(),gpu_selected_logits=f['router_logits'][row,actual[row]].float().tolist(),
    same_set=sorted(ids[row].tolist())==sorted(actual[row].tolist())))
  replay.append(dict(phase=phase,op='CPU softmax/Top8/renormalize of captured GPU logits',
   ids_exact=torch.equal(ids,f['actual_selected_experts']),weights_exact=torch.equal(weights,f['actual_final_weights']),
   probabilities_max_abs=float((prob-f['router_probabilities_fp32']).abs().max()),
   weights_max_abs=float((weights.float()-f['actual_final_weights'].float()).abs().max()),differing_id_rows=tied))
 bindings=root/'FIXTURE_WEIGHT_BINDINGS.json';binding=json.loads(bindings.read_text())
 rows.append(dict(root=name,request=rid,task_id=req['task_id'],prompt_tokens=req['prompt_tokens'],new_tokens=req['new_tokens'],
  manifest_checks=checks,fixture_schema=schema(fixtures),route_records=len(routes),expected_route_records=48*len(req['forwards']),
  all_routes_top8=all(r['selected_experts'].shape[-1]==8 for r in routes),weight_binding_sha256=sha(bindings),
  model_revision=binding['model_revision'],weight_keys=len(binding['layer0_weights']),router_replay=replay))
assert not torch.cuda.is_initialized()
result=dict(state='INSPECTED_EXISTING_REAL_FIXTURES_NOT_TARGET_EXECUTION',selection='fixed short request and first completed request of each old branch; no success selection',
 rows=rows,torch=torch.__version__,CPU_threads=1,cuda_initialized=False,NPU_runs=0,
 scope='selected request member hashes and real CPU router subchain; not all packet rehash, full layer or target timing')
(OUT/'REUSE_INSPECTION.json').write_text(json.dumps(result,indent=2))
print(json.dumps(dict(state=result['state'],rows=[dict(root=r['root'],hashes_match=all(x['matches'] for x in r['manifest_checks']),router_replay=r['router_replay']) for r in rows]),indent=2))
