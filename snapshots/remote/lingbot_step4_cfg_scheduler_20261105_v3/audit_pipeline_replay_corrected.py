
import os,sys,json,types,hashlib
from pathlib import Path
os.environ['CUDA_VISIBLE_DEVICES']='1'
import torch
B=Path('/mnt/sda1/h3240101068');R=Path(__file__).resolve().parent;C=B/'lingbot_step4_cfg_scheduler_20261105_v2'
A=Path('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe')
sys.path.insert(0,str(A/'source'))
from lingbot_video import LingBotVideoImageToVideoPipeline
from lingbot_video.scheduling_flow_unipc import FlowUniPCMultistepScheduler
torch.set_num_threads(4)
def load(p):return torch.load(p,map_location='cpu',weights_only=True)
class InjectedPrediction(torch.nn.Module):
 def __init__(self):
  super().__init__();self.register_parameter('identity',torch.nn.Parameter(torch.zeros(1,dtype=torch.bfloat16)))
  self.config=types.SimpleNamespace(in_channels=16);self.count=0
 def forward(self,*args,**kw):
  branch=['cond','uncond'][self.count];self.count+=1
  return (load(C/(branch+'_prediction.pt')).cuda(),)
class Replay(LingBotVideoImageToVideoPipeline):
 @property
 def _execution_device(self):return torch.device('cuda:0')
pipe=Replay(transformer=InjectedPrediction(),vae=None,text_encoder=None,processor=None,
 scheduler=FlowUniPCMultistepScheduler.from_pretrained(str(A/'model/scheduler'),local_files_only=True))
conditions=load(B/'lingbot_steps1_2_20261027_v1/conditions.pt')
original=pipe._apply_inpainting
scheduler_step=pipe.scheduler.step
checks={}
def step(*args,**kwargs):
 result=scheduler_step(*args,**kwargs)
 ref=load(R/'scheduler_CPU.pt')
 checks['scheduler_original_pipeline_bits']=torch.equal(result[0].cpu().view(torch.int32),ref.view(torch.int32))
 return result
pipe.scheduler.step=step
class Done(Exception):pass
def paint(x,c):
 y=original(x,c)
 if checks:
  ref=load(R/'next_latent_CPU.pt')
  checks['next_latent_original_pipeline_bits']=torch.equal(y.cpu().view(torch.int32),ref.view(torch.int32))
  torch.save(y.cpu(),R/'next_latent_original_pipeline_replay.pt')
  raise Done()
 return y
pipe._apply_inpainting=paint
from PIL import Image
pixel=pipe.preprocess_image(Image.open(A/'source/assets/cases/ti2v/example_4/first_frame.png').convert('RGB'),480,832).cuda()
try:
 with torch.no_grad():
  pipe(prompt='',image_tensor=pixel,
   cond_latent=conditions['cond_latent'].cuda(),
   prompt_embeds=conditions['prompt_embeds'].cuda(),prompt_mask=conditions['prompt_mask'].cuda(),
   negative_prompt_embeds=conditions['negative_embeds'].cuda(),negative_prompt_mask=conditions['negative_mask'].cuda(),
   latents=load(C/'scheduler_input_latent.pt').cuda(),
   height=480,width=832,num_frames=121,num_inference_steps=40,guidance_scale=3.0,shift=3.0,
   output_type='latent',batch_cfg=False)
except Done:pass
else:raise RuntimeError('first step stop missing')
assert pipe.transformer.count==2 and all(checks.values()),checks
out=dict(state='PASS_LIMITED_ORIGINAL_TI2V_PIPELINE_BOUNDARY_REPLAY',checks=checks,
 reference_injection='two captured full-transformer predictions and captured scheduler input latent',
 new_full_model_forwards=0,pipeline_source=str(A/'source/lingbot_video/pipeline_lingbot_video_i2v.py'))
(R/'PIPELINE_REPLAY_AUDIT.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out))
