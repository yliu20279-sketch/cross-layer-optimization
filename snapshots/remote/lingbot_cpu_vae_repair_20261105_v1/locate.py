
import os,sys,json,hashlib,traceback
from pathlib import Path
os.environ['CUDA_VISIBLE_DEVICES']='1'
import torch
from diffusers import AutoencoderKLWan
torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
B=Path('/mnt/sda1/h3240101068');R=Path(__file__).resolve().parent
A=Path('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe')
sys.path.insert(0,str(A/'source'))
from lingbot_video.pipeline_lingbot_video import LingBotVideoPipeline
x=torch.load(B/'lingbot_steps1_2_20261027_v1/attempt2/latent_40step.pt',weights_only=True)[:,:,:1]
vae=AutoencoderKLWan.from_pretrained(str(A/'model/vae'),torch_dtype=torch.float32,local_files_only=True)
pipe=LingBotVideoPipeline(transformer=None,vae=vae,text_encoder=None,processor=None,scheduler=None)
cpu=pipe._dit_latent_to_vae(x)
vae.cuda()
gpu=pipe._dit_latent_to_vae(x.cuda()).cpu()
def diff(a,b):
 mask=a.contiguous().view(torch.int32)!=b.contiguous().view(torch.int32)
 return dict(shape=list(a.shape),different_elements=int(mask.sum()),max_abs_diff=float((a-b).abs().max()),first_indices=torch.nonzero(mask)[:4].tolist())
report=dict(latent_conversion=diff(cpu,gpu),modules=[(n,type(m).__name__) for n,m in vae.named_modules()][:18])
torch.save(cpu,R/'conversion_CPU.pt');torch.save(gpu,R/'conversion_GPU.pt')
(R/'LOCATE.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
