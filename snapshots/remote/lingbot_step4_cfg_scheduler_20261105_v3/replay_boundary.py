
import os,sys,json,hashlib,copy,inspect
from pathlib import Path
os.environ['CUDA_VISIBLE_DEVICES']='1'
import torch,numpy as np
torch.set_num_threads(4)
B=Path('/mnt/sda1/h3240101068')
R=Path(__file__).resolve().parent
C=B/'lingbot_step4_cfg_scheduler_20261105_v2'
A=Path('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe')
sys.path.insert(0,str(A/'source'))
from lingbot_video.scheduling_flow_unipc import FlowUniPCMultistepScheduler
from lingbot_video.pipeline_lingbot_video import LingBotVideoPipeline
def save(name,x):
 x=x.detach().cpu().contiguous();torch.save(x,R/(name+'.pt'))
 return dict(file=name+'.pt',shape=list(x.shape),dtype=str(x.dtype),raw_sha256=hashlib.sha256(x.reshape(-1).view(torch.uint8).numpy().tobytes()).hexdigest())
def load(name):return torch.load(C/(name+'.pt'),map_location='cpu',weights_only=True)
def same(a,b):return torch.equal(a.contiguous().view(torch.int32),b.contiguous().view(torch.int32))
try:
 cond=load('cond_prediction');uncond=load('uncond_prediction')
 latent=load('scheduler_input_latent')
 mixed_original=load('scheduler_model_output_GPU')
 timestep=load('timestep')
 conditions=torch.load(B/'lingbot_steps1_2_20261027_v1/conditions.pt',weights_only=True)
 conditioning=conditions['cond_latent'].float()
 scheduler=FlowUniPCMultistepScheduler.from_pretrained(str(A/'model/scheduler'),local_files_only=True)
 scheduler.set_timesteps(40,device='cuda',shift=3.0)
 assert timestep.item()==scheduler.timesteps[0].item()
 gpu_cfg=uncond.cuda()+3.0*(cond.cuda()-uncond.cuda())
 # Independent CPU elementwise path preserves the original three FP32 operations.
 cpu_cfg=torch.from_numpy(uncond.numpy()+np.float32(3.0)*(cond.numpy()-uncond.numpy()))
 cfg_original_ok=same(gpu_cfg.cpu(),mixed_original)
 cfg_cpu_ok=same(cpu_cfg,gpu_cfg.cpu())
 state=copy.deepcopy(scheduler)
 for n,v in vars(state).items():
  if isinstance(v,torch.Tensor):setattr(state,n,v.cpu())
 gpu_step=scheduler.step(gpu_cfg,timestep.cuda(),latent.cuda(),return_dict=False)[0]
 cpu_step=state.step(cpu_cfg,timestep.cpu(),latent.clone(),return_dict=False)[0]
 step_ok=same(cpu_step,gpu_step.cpu())
 gpu_next=LingBotVideoPipeline._apply_inpainting(gpu_step.clone(),conditioning.cuda())
 cpu_next=cpu_step.clone()
 cpu_next[:,:,:conditioning.shape[2]]=conditioning
 next_ok=same(cpu_next,gpu_next.cpu())
 tensors={n:save(n,x) for n,x in [('cfg_CPU',cpu_cfg),('cfg_GPU',gpu_cfg),('scheduler_CPU',cpu_step),('scheduler_GPU',gpu_step),('next_latent_CPU',cpu_next),('next_latent_GPU',gpu_next)]}
 checks=dict(original_pipeline_cfg=cfg_original_ok,cpu_cfg=cfg_cpu_ok,scheduler=step_ok,next_latent=next_ok,finite=bool(torch.isfinite(cpu_next).all()),condition_prefix=same(cpu_next[:,:,:conditioning.shape[2]],conditioning))
 result=dict(state='PASS_LIMITED_CFG_SCHEDULER_NEXT_LATENT' if all(checks.values()) else 'FAIL_BOUNDARY_BITS',checks=checks,sample='example_4',step=0,next_step=1,schedule_steps=40,shift=3.0,guidance=3.0,refiner=False,target_GPU_count=0,reference_injection=['original encoder conditions and RNG','two newly captured complete GPU transformer outputs','original pipeline scheduler input latent and timestep'],scope='CPU functional boundary replay; no target simulator timing or full video',scheduler_class=type(scheduler).__name__,scheduler_source=inspect.getfile(type(scheduler)),pipeline_source=str(A/'source/lingbot_video/pipeline_lingbot_video.py'),timestep=float(timestep),timesteps=scheduler.timesteps.cpu().tolist(),tensors=tensors)
 (R/'BOUNDARY_AUDIT.json').write_text(json.dumps(result,indent=2))
 assert all(checks.values()),checks
 print(json.dumps(result))
except BaseException:
 import traceback
 (R/'FAILURE.json').write_text(json.dumps(dict(error=traceback.format_exc()),indent=2))
 raise
