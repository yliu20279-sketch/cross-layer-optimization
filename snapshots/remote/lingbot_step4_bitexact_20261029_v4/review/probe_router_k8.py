"""Input-independent FP32 K8 primitive characterization; not model inference."""
import os
os.environ['CUDA_VISIBLE_DEVICES']='1'
import torch,numpy as np,pathlib,json,time
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');D=P/'router_k8_probe';D.mkdir(exist_ok=False)
torch.set_num_threads(1);torch.set_grad_enabled(False);torch.backends.cuda.matmul.allow_tf32=False
rng=np.random.default_rng(20261030);xs=rng.standard_normal((16,8),dtype=np.float32);ws=rng.standard_normal((16,128,8),dtype=np.float32)
xs*=np.exp2(rng.integers(-4,5,xs.shape).astype(np.float32));ws*=np.exp2(rng.integers(-4,5,ws.shape).astype(np.float32))
x=torch.zeros((49883,2048),device='cuda');w=torch.zeros((128,2048),device='cuda');ys=[]
for p in range(16):
 x.zero_();w.zero_();x[:,:8]=torch.from_numpy(xs[p]).cuda();w[:,:8]=torch.from_numpy(ws[p]).cuda()
 if p==0:
  with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as prof:y=x@w.T;torch.cuda.synchronize()
  prof.export_chrome_trace(str(D/'trace.json'))
 else:y=x@w.T
 ys.append(y[:128].cpu().numpy())
np.savez(D/'probe.npz',x=xs,w=ws,y=np.stack(ys))
(D/'RESULT.json').write_text(json.dumps(dict(status='PRIMITIVE_IDENTIFICATION_ONLY',model_input_read=False,patterns=16,shape=[49883,128,2048],nonzero_K=[0,8],peak_GPU_bytes=torch.cuda.max_memory_allocated(),target_GPU_count=0),indent=2))
