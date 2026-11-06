import ctypes as C,hashlib,json,sys
from pathlib import Path
import numpy as np
import torch
torch.set_num_threads(1)
R=Path(__file__).resolve().parent;A=R/'attempt1';B=R.parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
result=json.loads((A/'RESULTS.json').read_text());ids=np.fromfile(A/'new_IDs.bin',dtype='<i8').reshape(-1,8)
weights=np.fromfile(A/'new_weights_BF16.bin',dtype='<u2').reshape(-1,8)
gold_ids=[];gold_w=[];probs=[];logits=[]
for binding in json.loads((A/'INPUT_BINDINGS.json').read_text()):
 p=B/binding['root']/'requests'/binding['request']/'layer0_actual_fixtures.pt';assert sha(p)==binding['fixture_sha256']
 fs=torch.load(p,weights_only=True,map_location='cpu');phases=[]
 for phase,f in fs.items():
  if phase=='prefill_chunks':phases.extend(v for k,v in sorted(f.items(),key=lambda x:int(x[0])))
  else:phases.append(f)
 for f in phases:
  gold_ids.append(f['actual_selected_experts']);gold_w.append(f['actual_final_weights']);probs.append(f['router_probabilities_fp32']);logits.append(f['router_logits'])
gold=torch.cat(gold_ids);gw=torch.cat(gold_w);p=torch.cat(probs);logit=torch.cat(logits)
assert ids.shape==(759,8) and np.array_equal(ids,gold.numpy()) and np.array_equal(weights,gw.view(torch.uint16).numpy())
assert (A/'real_logits_BF16.bin').read_bytes()==logit.contiguous().view(torch.uint16).numpy().tobytes()
assert all(len(set(row))==8 and min(row)>=0 and max(row)<128 for row in ids.tolist())
order=torch.sort(p,descending=True).values;internal=(order[:,:7]==order[:,1:8]).any(-1);boundary=order[:,7]==order[:,8];non=~(internal|boundary)
selected=p.gather(1,gold);assert bool((selected[:,:-1]>=selected[:,1:]).all())
assert bool((selected>=order[:,7:8]).all())
for i,row in enumerate(ids):
 threshold=order[i,7];strict=set(torch.where(p[i]>threshold)[0].tolist());equals=torch.where(p[i]==threshold)[0].tolist()
 required=strict|set(equals[:8-len(strict)]);assert set(row)==required
stable=torch.argsort(p,descending=True,stable=True)[:,:8];stable_bad=int((stable!=gold).any(-1).sum())
assert stable_bad==151 and int(non.sum())==486 and int(boundary.sum())==80 and int(internal.sum())==206
assert result['captured_probability_selector_all_exact'] and result['new_softmax_route_all_exact'] and not result['GPU_FP32_probability_all_exact']
assert max(x['FP32_probabilities_max_abs'] for x in result['rows'])==1.4901161193847656e-7
for file in ['PRE_RUN_FREEZE.json','ROI_FREEZE.json']:
 for n,h in json.loads((R/file).read_text()).items():assert sha(R/n)==h
headers=Path(torch.__file__).parent/'include/ATen/native/cuda'
source_headers={str(headers/n):sha(headers/n) for n in ['SortUtils.cuh','SortingCommon.cuh','Sort.h']}
report=dict(state='PASS_LIMITED_TOP8_ID_SLOT_WEIGHT_IDENTITY_WITH_SOFTMAX_FP32_DIFFERENCES',real_tokens=759,non_tied_rows=486,internal_tie_rows=206,boundary_tie_rows=80,
 tie_categories_overlap_rows=int((internal&boundary).sum()),all_real_IDs_and_BF16_weights_exact=True,strict_winners_and_first_boundary_equal_membership=True,
 stable_expert_ID_tie_negative_control_bad_rows=stable_bad,FP32_softmax_GPU_exact=False,max_FP32_probability_abs_error=1.4901161193847656e-7,
 torch=str(torch.__version__),torch_git_version=torch.version.git_version,torch_compiled_cuda=torch.version.cuda,installed_source_headers=source_headers,
 scope='finite E128/k8, frozen v2.6 CUDA behavior on fixed real fixtures; host CPU fallback, not NPU TopK instruction certification')
out=Path(sys.argv[1]) if len(sys.argv)>1 else A/'INDEPENDENT_AUDIT.json'
out.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
