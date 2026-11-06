import hashlib,json
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;O=R/'attempt1'
def j(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(R/n)==h for n,h in j(R/'FREEZE.json').items())
files=j(O/'FILES.json');data={}
for v in files:
 p=O/v['path'];assert p.stat().st_size==v['bytes'] and sha(p)==v['sha256']
 dtype={'torch.float32':'<f4','torch.bfloat16':'<u2','torch.int64':'<i8'}[v['dtype']];data[v['device'],v['stage']]=np.frombuffer(p.read_bytes(),dtype=dtype).reshape(v['shape'])
checks=j(O/'CHECKS.json');free=[c for c in checks if c['scope']=='free_running_CPU_vs_GPU']
for c in free:
 a=data['cpu',c['name']];b=data['gpu',c['name']];assert int((a!=b).sum())==c['different']
assert next(c['name'] for c in free if c['different'])=='input_norm.variance'
assert np.array_equal(data['cpu','input_norm.output'],data['gpu','input_norm.output'])
assert next(c['name'] for c in free if c['different'] and c['dtype']=='torch.bfloat16')=='q_proj'
assert all(c['exact'] for c in checks if c['scope']=='capture_identity')
old=R.parent/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1';oldfiles=j(old/'FILES.json');bound=[]
for oldname,newname in [('input','input'),('input_norm','input_norm.output'),('attention_output','attention_output'),('pre_MoE_residual','attention_residual'),('post_attention_norm','post_norm.output'),('router_logits','router_logits'),('router_probabilities','router_softmax_fp32'),('route_IDs','route_IDs'),('route_weights','route_weights')]:
 v=next(x for x in oldfiles if x['phase']=='prefill' and x['layer']==0 and x['stage']==oldname);new=next(x for x in files if x['device']=='cpu' and x['stage']==newname);assert (old/v['path']).read_bytes()==(O/new['path']).read_bytes();bound.append(oldname)
def fp(bits):return (bits.astype('<u4')<<16).view('<f4')
cpu=data['cpu','route_IDs'];gpu=data['gpu','route_IDs'];assert int((cpu!=gpu).sum())==10
rows=[];cl=fp(data['cpu','router_logits']).reshape(19,128);gl=fp(data['gpu','router_logits']).reshape(19,128)
for t in np.where((cpu!=gpu).any(-1))[0]:
 c=cpu[t];g=gpu[t];sort=np.sort(gl[t])[::-1];cs=np.sort(cl[t])[::-1]
 rows.append(dict(token=int(t),CPU=c.tolist(),GPU=g.tolist(),different_slots=int((c!=g).sum()),same_expert_set=bool(np.array_equal(np.sort(c),np.sort(g))),GPU_boundary_tie=bool(sort[7]==sort[8]),CPU_boundary_tie=bool(cs[7]==cs[8]),GPU_logits_for_GPU_slots=gl[t,g].tolist(),CPU_logits_for_GPU_slots=cl[t,g].tolist()))
out=dict(state='PASS_LIMITED_FIRST_DIFFERENCE_AUDIT',payload_files=len(files),free_comparisons=len(free),CPU_stage_bindings_to_prior_two_layer_run=bound,first_internal_operator='input_RMSNorm FP32 mean(square)',internal_variance_different=9,internal_difference_survives_input_BF16=False,first_persistent_BF16_operator='Q/K/V projection GEMM',projection_differences=[74,5,3],capture_identity_checks=4,original_output_differences_unchanged=4249,original_route_differences=10,route_rows=rows,scope='local file arithmetic audit; equal-input GPU operator probes executed remotely; no universal GEMM cause or implementation fix certified')
(R/'LOCAL_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
