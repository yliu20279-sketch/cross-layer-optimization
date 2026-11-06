
import os,sys,json
from pathlib import Path
os.environ['CUDA_VISIBLE_DEVICES']='1'
import torch,numpy as np
from diffusers import AutoencoderKLWan
R=Path(__file__).resolve().parent;B=R.parent
A=Path('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe')
sys.path.insert(0,str(A/'source'))
from lingbot_video.pipeline_lingbot_video import LingBotVideoPipeline
torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
torch.cuda.set_per_process_memory_fraction(0.25,0)
vae=AutoencoderKLWan.from_pretrained(str(A/'model/vae'),torch_dtype=torch.float32,local_files_only=True).cuda()
pipe=LingBotVideoPipeline(transformer=None,vae=vae,text_encoder=None,processor=None,scheduler=None)
x=torch.load(B/'lingbot_steps1_2_20261027_v1/attempt2/latent_40step.pt',weights_only=True)[:,:,:1]
with torch.no_grad():a=pipe._decode_latents(x.cuda())[0][0]
np.save(R/'GPU_prefix_frame.npy',a)
ref=np.load(B/'lingbot_step4_vae_20261105_v1/frames_FP32.npy',mmap_mode='r')[0]
cpu=np.fromfile(R/'case1/N00/output1.bin',np.float32).reshape(a.shape)
out=dict(state='VAE_PREFIX_DIAGNOSTIC',gpu_prefix_vs_full_gpu_raw_differences=int(np.count_nonzero(a.view(np.uint32)!=ref.copy().view(np.uint32))),gpu_prefix_vs_full_gpu_max_abs=float(np.max(np.abs(a-ref))),cpu_vs_gpu_prefix_raw_differences=int(np.count_nonzero(cpu.view(np.uint32)!=a.view(np.uint32))),cpu_vs_gpu_prefix_max_abs=float(np.max(np.abs(cpu-a))),new_external_VAE_prefix_decodes=1,target_GPU_count=0)
(R/'VAE_PREFIX_DIAGNOSTIC.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out))
