
import os,sys,time,json,copy
from pathlib import Path
import torch,numpy as np
torch.set_num_threads(4)
R=Path(sys.argv[1]);D=Path(sys.argv[2]);op=int(sys.argv[3])
A=Path('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe')
B=R.parent;sys.path.insert(0,str(A/'source'))
started=time.time()
if op==0:
 from lingbot_video.scheduling_flow_unipc import FlowUniPCMultistepScheduler
 data=np.fromfile(D/'input.bin',np.float32).reshape(3,1,16,2,8,8)
 c,u,x=[torch.from_numpy(v.copy()) for v in data]
 cfg=u+3.0*(c-u)
 scheduler=FlowUniPCMultistepScheduler.from_pretrained(str(A/'model/scheduler'),local_files_only=True)
 scheduler.set_timesteps(40,device='cpu',shift=3.0)
 raw=scheduler.step(cfg,scheduler.timesteps[0],x,return_dict=False)[0]
 nxt=raw.clone()
 conditions=torch.load(B/'lingbot_steps1_2_20261027_v1/conditions.pt',weights_only=True)['cond_latent'].float()
 nxt[:,:,:1]=conditions[:,:,:1,:8,:8]
 np.concatenate([v.numpy().reshape(-1) for v in (cfg,raw,nxt)]).astype('<f4').tofile(D/'output.bin')
else:
 sys.path.insert(0,str(R/"compat"))
 import ordered_ops_attention;ordered_ops_attention.install()
 from diffusers import AutoencoderKLWan
 from lingbot_video.pipeline_lingbot_video import LingBotVideoPipeline
 latent=torch.from_numpy(np.fromfile(D/'input.bin',np.float32).copy().reshape(1,16,1,60,104))
 vae=AutoencoderKLWan.from_pretrained(str(A/'model/vae'),torch_dtype=torch.float32,local_files_only=True)
 pipe=LingBotVideoPipeline(transformer=None,vae=vae,text_encoder=None,processor=None,scheduler=None)
 with torch.no_grad():frame=pipe._decode_latents(latent)[0]
 assert frame.shape==(1,480,832,3) and np.isfinite(frame).all()
 frame.astype('<f4').tofile(D/'output.bin')
(D/'CPU_RECEIPT.json').write_text(json.dumps(dict(op=op,wall_seconds=time.time()-started,CPU_target_cost_ns=None,backend='native CPU FP32 software service; no Sniper cost model',GPU_count=0),indent=2))
