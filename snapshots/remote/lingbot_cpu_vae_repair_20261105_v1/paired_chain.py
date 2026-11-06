import os;os.environ['CUDA_VISIBLE_DEVICES']='1'
import torch,threading,queue,json,time
from pathlib import Path
from diffusers import AutoencoderKLWan
import ordered_ops_attention;ordered_ops_attention.install()
torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
R=Path(__file__).resolve().parent;A='/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe/model/vae'
cpu=AutoencoderKLWan.from_pretrained(A,torch_dtype=torch.float32,local_files_only=True);gpu=AutoencoderKLWan.from_pretrained(A,torch_dtype=torch.float32,local_files_only=True).cuda()
x=torch.load(R/'conversion_GPU.pt',weights_only=True).contiguous(memory_format=torch.channels_last_3d)
q=queue.Queue(1);ack=threading.Event();stop=threading.Event();rows=[]
class Stop(Exception):pass
def cpu_hook(name):
 def h(module,args,kwargs,result):
  if not isinstance(result,torch.Tensor):return
  ack.clear();q.put((name,result.detach().clone(),tuple(result.stride()),[a.detach().clone() if isinstance(a,torch.Tensor) else a for a in args]));ack.wait(600)
  if stop.is_set():raise Stop()
 return h
def gpu_hook(name):
 def h(module,args,kwargs,result):
  if not isinstance(result,torch.Tensor):return
  n,a,st,ca=q.get(timeout=600);assert n==name,(n,name);b=result.detach().cpu();diff=int((a.contiguous().view(torch.int32)!=b.contiguous().view(torch.int32)).sum());row=dict(name=name,type=type(module).__name__,diff=diff,elements=a.numel(),CPU_stride=st,GPU_stride=result.stride(),max_abs=float((a-b).abs().max()));rows.append(row);print(row,flush=True)
  if diff:
   torch.save(dict(CPU=a,GPU=b,CPU_args=ca,GPU_args=[v.detach().cpu() if isinstance(v,torch.Tensor) else v for v in args],state=module.state_dict()),R/'PAIRED_FIRST.pt');stop.set();ack.set();raise Stop()
  ack.set()
 return h
for n,m in cpu.named_modules():m.register_forward_hook(cpu_hook(n),with_kwargs=True)
for n,m in gpu.named_modules():m.register_forward_hook(gpu_hook(n),with_kwargs=True)
def run_cpu():
 try:
  with torch.no_grad():cpu.decode(x)
 except Stop:pass
 except BaseException as e:print('CPU_EXCEPTION',repr(e),flush=True);stop.set();ack.set()
t=threading.Thread(target=run_cpu);t.start()
try:
 with torch.no_grad():gpu.decode(x.cuda())
except Stop:pass
finally:stop.set();ack.set();t.join(timeout=30)
(R/'PAIRED_CHAIN_AUDIT.json').write_text(json.dumps(dict(state='FAIL_FIRST_DIVERGENCE' if any(r['diff'] for r in rows) else 'PASS_BITWISE',operators=rows),indent=2))
