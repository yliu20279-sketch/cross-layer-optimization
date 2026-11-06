
import os,sys,copy,json
from pathlib import Path
os.environ['CUDA_VISIBLE_DEVICES']='1'
import torch
from diffusers import AutoencoderKLWan
import ordered_ops_allconv;ordered_ops_allconv.install()
torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
B=Path('/mnt/sda1/h3240101068');R=Path(__file__).resolve().parent
vae=AutoencoderKLWan.from_pretrained('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe/model/vae',torch_dtype=torch.float32,local_files_only=True).cuda()
x=torch.load(R/'conversion_GPU.pt',weights_only=True).cuda().contiguous(memory_format=torch.channels_last_3d)
rows=[]
class Stop(Exception):pass
def cpu(v):
 if isinstance(v,torch.Tensor):return v.detach().cpu()
 if isinstance(v,list):return [cpu(z) for z in v]
 if isinstance(v,tuple):return tuple(cpu(z) for z in v)
 if isinstance(v,dict):return {k:cpu(z) for k,z in v.items()}
 return v
def hook(name):
 def compare(module,args,kwargs,result):
  if not isinstance(result,torch.Tensor):return
  replica=copy.deepcopy(module).cpu()
  for child in replica.modules():child._forward_hooks.clear()
  with torch.no_grad():actual=replica(*cpu(args),**cpu(kwargs))
  ref=result.detach().cpu()
  bad=actual.contiguous().view(torch.int32)!=ref.contiguous().view(torch.int32)
  row=dict(name=name,type=type(module).__name__,different_elements=int(bad.sum()),elements=bad.numel(),max_abs_diff=float((actual-ref).abs().max()),input_shapes=[list(a.shape) for a in args if isinstance(a,torch.Tensor)])
  rows.append(row)
  if bad.any():
   torch.save(dict(args=cpu(args),kwargs=cpu(kwargs),state=replica.state_dict(),CPU=actual,GPU=ref),R/'NEXT4_OPERATOR.pt')
   row['module_repr']=str(module)
   (R/'NEXT4_OPERATOR.json').write_text(json.dumps(dict(state='FIRST_SAME_INPUT_OPERATOR_DIFFERENCE',prior_conversion_bitwise_equal=True,operators=rows),indent=2))
   raise Stop()
 return compare
for name,module in vae.named_modules():
 if name and (not list(module.children()) or type(module).__name__=="WanAttentionBlock"):module.register_forward_hook(hook(name),with_kwargs=True)
try:
 with torch.no_grad():vae.decode(x)
except Stop:pass
else:(R/'NEXT4_OPERATOR.json').write_text(json.dumps(dict(state='NO_LEAF_DIFFERENCE',operators=rows),indent=2))
print((R/'NEXT4_OPERATOR.json').read_text())
