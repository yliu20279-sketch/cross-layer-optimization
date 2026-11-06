
import os,json
os.environ['CUDA_VISIBLE_DEVICES']='1'
import torch
from pathlib import Path
from torch.profiler import profile,ProfilerActivity
torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
R=Path(__file__).resolve().parent
d=torch.load(R/'FIRST_OPERATOR.pt',weights_only=True)
x=d['args'][0];w=d['state']['weight'];b=d['state']['bias'];ref=d['GPU']
def report(name,y):
 bad=y.contiguous().view(torch.int32)!=ref.contiguous().view(torch.int32)
 return dict(name=name,different_elements=int(bad.sum()),max_abs_diff=float((y-ref).abs().max()))
rows=[]
for mkldnn in (True,False):
 torch.backends.mkldnn.enabled=mkldnn
 for layout in ('contiguous','channels_last_3d'):
  a=x.contiguous(memory_format=torch.channels_last_3d if layout=='channels_last_3d' else torch.contiguous_format)
  a=torch.nn.functional.pad(a,(1,1,1,1,2,0))
  for separate in (False,True):
   y=torch.nn.functional.conv3d(a,w,None if separate else b)
   if separate:y=y+b[None,:,None,None,None]
   rows.append(report(str((mkldnn,layout,separate)),y))
a=torch.nn.functional.pad(x.cuda().contiguous(memory_format=torch.channels_last_3d),(1,1,1,1,2,0))
with profile(activities=[ProfilerActivity.CPU,ProfilerActivity.CUDA]) as p:
 y=torch.nn.functional.conv3d(a,w.cuda(),b.cuda())
 torch.cuda.synchronize()
kernels=sorted(set(e.name for e in p.events() if e.device_type==torch.autograd.DeviceType.CUDA))
(R/'CONV_VARIANTS.json').write_text(json.dumps(dict(variants=rows,kernels=kernels,gpu_same_input=report('GPU_repeat',y.cpu())),indent=2))
print((R/'CONV_VARIANTS.json').read_text())
