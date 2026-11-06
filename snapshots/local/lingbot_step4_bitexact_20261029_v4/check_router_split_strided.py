import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='4'
import torch,pathlib,json,ctypes,itertools,numpy as np
from safetensors import safe_open
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');G=P.parent/'lingbot_step3_capture_20261028_v1';torch.set_num_threads(4)
r=next(r for r in json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'] if r['name']=='blocks.0.ffn.router.weight')
with safe_open(r['canonical_file'],framework='pt',device='cpu') as f:w=f.get_tensor(r['name']).contiguous()
lib=ctypes.CDLL(str(P/'librouter_split_strided.so'));lib.split.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int]*5
results=[]
for branch in ['cond','uncond']:
 x=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_ffn_input.pt'),weights_only=True)[0];idx=torch.tensor(list(range(32))+list(range(len(x)-32,len(x))));x=x[idx].float().contiguous();gold=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_router_logits.pt'),weights_only=True)[idx]
 for tile in [8,16,32,64,128]:
  a=torch.empty((5,64,128));lib.split(x.data_ptr(),w.data_ptr(),a.data_ptr(),64,128,2048,5,tile)
  best=8193;orders=[]
  for order in itertools.permutations(range(5)):
   y=a[order[0]].clone()
   for p in order[1:]:y=y+a[p]
   bad=int((y.view(torch.int32)!=gold.view(torch.int32)).sum())
   if bad<best:best=bad;orders=[order]
   elif bad==best:orders.append(order)
  r=dict(branch=branch,tile=tile,mismatches=best,orders=orders);results.append(r);print(json.dumps(r),flush=True)
(P/'ROUTER_SPLIT_STRIDED_RESULT.json').write_text(json.dumps(results,indent=2))

