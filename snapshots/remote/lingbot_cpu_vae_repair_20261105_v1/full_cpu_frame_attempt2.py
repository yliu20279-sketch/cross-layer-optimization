import os,time,json
os.environ['CUDA_VISIBLE_DEVICES']=''
from pathlib import Path
import torch,numpy as np
import ordered_ops_attention;ordered_ops_attention.install()
from diffusers import AutoencoderKLWan
R=Path(__file__).resolve().parent;B=R.parent;A=Path('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe')
import sys;sys.path.insert(0,str(A/'source'))
from lingbot_video.pipeline_lingbot_video import LingBotVideoPipeline
torch.set_num_threads(4);started=time.time()
x=torch.load(B/'lingbot_steps1_2_20261027_v1/attempt2/latent_40step.pt',weights_only=True).float()[:,:,:1]
vae=AutoencoderKLWan.from_pretrained(str(A/'model/vae'),torch_dtype=torch.float32,local_files_only=True)
pipe=LingBotVideoPipeline(transformer=None,vae=vae,text_encoder=None,processor=None,scheduler=None)
with torch.no_grad():a=pipe._decode_latents(x)[0][0]
b=np.load(B/'lingbot_step4_vae_20261105_v1/frames_FP32.npy',mmap_mode='r')[0]
np.save(R/'REPAIRED_CPU_FIRST_FRAME_attempt2.npy',a)
bad=a.view(np.uint32)!=b.view(np.uint32)
row=dict(state='PASS_BITWISE' if not bad.any() else 'FAIL_BITWISE',different_elements=int(bad.sum()),elements=a.size,max_abs_diff=float(np.max(np.abs(a-b))),u8_differences=int(np.count_nonzero(np.round(a*255).astype(np.uint8)!=np.round(b*255).astype(np.uint8))),wall_seconds=time.time()-started,target_GPU_calls=0,reference_output_used_for_computation=False,reference_injection='frozen final latent at DiT-to-VAE; only first temporal slice decoded')
(R/'FULL_CPU_FRAME_attempt2_AUDIT.json').write_text(json.dumps(row,indent=2));print(row,flush=True);assert not bad.any()
