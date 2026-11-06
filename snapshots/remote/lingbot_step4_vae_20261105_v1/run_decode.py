
import os,sys,time,json,hashlib,traceback
from pathlib import Path
os.environ['CUDA_VISIBLE_DEVICES']='1'
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
import torch,numpy as np
from PIL import Image
from diffusers import AutoencoderKLWan
from diffusers.utils import export_to_video
B=Path('/mnt/sda1/h3240101068');R=Path(__file__).resolve().parent
F=B/'lingbot_steps1_2_20261027_v1/attempt2'
A=Path('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe')
sys.path.insert(0,str(A/'source'))
from lingbot_video.pipeline_lingbot_video import LingBotVideoPipeline
def put(n,v):(R/n).write_text(json.dumps(v,indent=2))
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
started=time.time()
try:
 torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
 torch.cuda.set_device(0)
 free,total=torch.cuda.mem_get_info()
 assert free>34*2**30,free
 torch.cuda.set_per_process_memory_fraction(0.44,0)
 latent=torch.load(F/'latent_40step.pt',map_location='cpu',weights_only=True)
 prior=json.loads((F/'REFERENCE_RUNS.json').read_text())['40']
 assert hashlib.sha256(latent.numpy().tobytes()).hexdigest()==prior['sha256_raw_FP32']
 assert list(latent.shape)==[1,16,31,60,104] and latent.dtype==torch.float32 and torch.isfinite(latent).all()
 files=[F/'latent_40step.pt',F/'REFERENCE_RUNS.json',F/'FINAL_REFERENCE.json',F/'first_output_frame.png',F/'reference_40step.mp4',A/'model/vae/config.json',A/'model/vae/diffusion_pytorch_model.safetensors',A/'source/lingbot_video/pipeline_lingbot_video.py']
 put('INPUT_BINDING.json',dict(sample='example_4',precision='VAE FP32 unchanged',target_GPU_count=0,
  external_reference_GPU=1,injection='frozen original 40-step final DiT latent directly into VAE conversion/decode',
  latent_raw_sha256=prior['sha256_raw_FP32'],
  files=[dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for p in files]))
 put('STATUS.json',dict(state='LOADING_ORIGINAL_FP32_VAE'))
 vae=AutoencoderKLWan.from_pretrained(str(A/'model/vae'),torch_dtype=torch.float32,local_files_only=True).to('cuda')
 assert next(vae.parameters()).dtype==torch.float32
 pipe=LingBotVideoPipeline(transformer=None,vae=vae,text_encoder=None,processor=None,scheduler=None)
 torch.cuda.reset_peak_memory_stats()
 put('STATUS.json',dict(state='RUNNING_ORIGINAL_VAE_DECODE'))
 with torch.no_grad():frames=pipe._decode_latents(latent.cuda())[0]
 torch.cuda.synchronize()
 assert frames.shape==(121,480,832,3) and frames.dtype==np.float32 and np.isfinite(frames).all()
 assert frames.min()>=0 and frames.max()<=1
 np.save(R/'frames_FP32.npy',frames)
 rows=[dict(index=i,shape=list(x.shape),dtype=str(x.dtype),sha256_raw_fp32=hashlib.sha256(np.ascontiguousarray(x).tobytes()).hexdigest()) for i,x in enumerate(frames)]
 put('FRAME_MANIFEST.json',rows)
 pixels=(np.clip(frames[0],0,1)*255).round().astype('uint8')
 Image.fromarray(pixels).save(R/'first_output_frame.png')
 original=np.asarray(Image.open(F/'first_output_frame.png').convert('RGB'))
 first_equal=np.array_equal(pixels,original)
 export_to_video(frames,str(R/'decoded_40step.mp4'),fps=24)
 import imageio.v2 as iio
 old=iio.get_reader(str(F/'reference_40step.mp4'))
 new=iio.get_reader(str(R/'decoded_40step.mp4'))
 comparisons=[]
 from itertools import zip_longest
 for i,(x,y) in enumerate(zip_longest(old,new)):
  assert x is not None and y is not None
  assert x.shape==y.shape==(480,832,3)
  delta=np.abs(x.astype(np.int16)-y.astype(np.int16))
  comparisons.append(dict(index=i,equal=bool(np.array_equal(x,y)),different_values=int(np.count_nonzero(delta)),max_abs_diff=int(delta.max()),old_sha256=hashlib.sha256(x.tobytes()).hexdigest(),new_sha256=hashlib.sha256(y.tobytes()).hexdigest()))
 old.close();new.close()
 assert len(comparisons)==121
 put('VIDEO_FRAME_COMPARISON.json',comparisons)
 exact=first_equal and all(v['equal'] for v in comparisons)
 audit=dict(state='PASS_LIMITED_FROZEN_LATENT_VAE_OUTPUT' if exact else 'FAIL_FRAME_DIFFERENCE_PRESERVED',
  original_first_frame_pixels_equal=first_equal,all121_decoded_video_frames_equal=all(v['equal'] for v in comparisons),
  raw_previous_full_frames_available=False,new_frame_hashes=121,shape=list(frames.shape),dtype=str(frames.dtype),
  finite=True,value_range=[float(frames.min()),float(frames.max())],fps=24,
  injection='original frozen final DiT latent; no target DiT output substituted',
  target_GPU_count=0,new_external_VAE_decodes=1,new_full_Transformer_forwards=0,
  peak_GPU_allocated_bytes=torch.cuda.max_memory_allocated(),elapsed_seconds=time.time()-started,
  scope='original GPU VAE functional replay; compressed-video comparison and first-frame exact pixels; not target VAE timing or all-frame raw-reference bit certification')
 put('VAE_AUDIT.json',audit);put('STATUS.json',dict(state=audit['state']))
 assert exact,audit
 print(json.dumps(audit))
except BaseException:
 put('FAILURE.json',dict(error=traceback.format_exc(),elapsed=time.time()-started))
 put('STATUS.json',dict(state='STOPPED_FAILURE_PRESERVED'))
 raise
