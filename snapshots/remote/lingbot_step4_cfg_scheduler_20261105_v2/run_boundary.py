"""External Golden-generation only. This GPU is NOT part of the target model."""
import os,sys,time,json,pathlib,traceback,hashlib,gc,subprocess
ROOT=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_cfg_scheduler_20261105_v2')
ROOT.mkdir(exist_ok=True)
ASSET=pathlib.Path('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe')
sys.path.insert(0,str(ASSET/'source'))
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['DIFFUSERS_ATTN_BACKEND']='_native_flash'
os.environ['LINGBOT_MOE_EXPERT_BACKEND']='grouped_mm'  # source fallback when API absent
os.environ['LINGBOT_MOE_PAD_BACKEND']='vectorized'
os.environ['LINGBOT_MOE_RESTORE_BACKEND']='chunked_scatter'
os.environ['LINGBOT_MOE_RESTORE_CHUNK_SIZE']='128'
os.environ['TOKENIZERS_PARALLELISM']='false'

def write(name,obj):
    (ROOT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf8')
def log(msg):print(time.strftime('%Y-%m-%d %H:%M:%S'),msg,flush=True)
def snapshot(stage,**kw):
    write('REFERENCE_STATUS.json',dict(stage=stage,time=time.time(),target_gpu_count=0,external_reference_gpu='physical index1 only',**kw));log(stage)

started=time.time()
try:
    import torch,numpy as np
    from PIL import Image
    from lingbot_video import LingBotVideoTransformer3DModel,LingBotVideoImageToVideoPipeline
    from lingbot_video.pipeline_lingbot_video import DEFAULT_NEGATIVE_PROMPT
    from lingbot_video.runner import _caption_from_sample
    from diffusers.utils import export_to_video
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32=False
    torch.backends.cudnn.allow_tf32=False
    torch.cuda.set_device(0)
    assert os.environ.get('CUDA_VISIBLE_DEVICES')=='1'
    free,total=torch.cuda.mem_get_info();assert free>76*2**30,('reference GPU busy',free)
    torch.cuda.set_per_process_memory_fraction(0.98,0)
    snapshot('LOAD_CPU',torch=torch.__version__,reference_free_bytes=free)
    transformer=LingBotVideoTransformer3DModel.from_pretrained(str(ASSET/'model'),subfolder='transformer',torch_dtype=torch.bfloat16,local_files_only=True)
    pipe=LingBotVideoImageToVideoPipeline.from_pretrained(str(ASSET/'model'),transformer=transformer,
         torch_dtype={'default':torch.bfloat16,'transformer':torch.bfloat16,'text_encoder':torch.bfloat16,'vae':torch.float32},local_files_only=True,trust_remote_code=True)
    class ExternalStagedPipeline(LingBotVideoImageToVideoPipeline):
        @property
        def _execution_device(self):
            return torch.device('cuda:0')
    pipe.__class__=ExternalStagedPipeline
    assert pipe._execution_device==torch.device('cuda:0')
    # Residency-only changes; all numeric modules and source files remain untouched.
    sample_path=ASSET/'source/assets/cases/ti2v/example_4/prompt.json'
    image_path=sample_path.parent/'first_frame.png'
    sample=json.loads(sample_path.read_text());prompt=_caption_from_sample(sample)
    image=Image.open(image_path).convert('RGB')
    dtypes={name:{str(dt):sum(p.numel() for p in mod.parameters() if p.dtype==dt) for dt in set(p.dtype for p in mod.parameters())} for name,mod in [('transformer',pipe.transformer),('text_encoder',pipe.text_encoder),('vae',pipe.vae)]}
    assert pipe.transformer.blocks[0].ffn.router.weight.dtype==torch.float32
    assert pipe.transformer.blocks[0].ffn.experts.w1.dtype==torch.bfloat16
    assert next(pipe.vae.parameters()).dtype==torch.float32
    write('LOADED_DTYPE_AUDIT.json',dtypes)
    write('ENVIRONMENT.json',dict(torch=torch.__version__,cuda=torch.version.cuda,target_has_GPU=False,
         reference_GPU=torch.cuda.get_device_name(0),CUDA_VISIBLE_DEVICES=os.environ['CUDA_VISIBLE_DEVICES'],
         source_torch_recommendation='2.12 nightly cu130',actual_torch_path='2.6 cu124 supported source per-expert fallback',
         grouped_mm_available=hasattr(torch,'_grouped_mm'),attention='_native_flash',restore='chunked_scatter128',
         note='External reference variant, not author benchmark or target timing'))
    subprocess.run([sys.executable,'-m','pip','freeze'],stdout=(ROOT/'pip_freeze.txt').open('w'),check=True)
    snapshot('REUSE_FROZEN_SOURCE_CONDITIONS')
    cache=torch.load(pathlib.Path('/mnt/sda1/h3240101068/lingbot_steps1_2_20261027_v1/conditions.pt'),map_location='cpu',weights_only=True)
    pe=cache['prompt_embeds'].to('cuda');pm=cache['prompt_mask'].to('cuda')
    ne=cache['negative_embeds'].to('cuda');nm=cache['negative_mask'].to('cuda')
    cond=cache['cond_latent'].to('cuda');rng_after_encode=cache['rng_after_encode']
    pixel=pipe.preprocess_image(image,480,832).to(device='cuda',dtype=torch.float32)
    write('CONDITION_SHAPES.json',dict(prompt=list(pe.shape),negative=list(ne.shape),cond_latent=list(cond.shape),video_tokens=48360,joint_tokens_cond=48360+pe.shape[1],joint_tokens_uncond=48360+ne.shape[1],cached_conditions_from='attempt1 original source encoders/RNG'))
    pipe.transformer.to('cuda')
    calls=[]
    def hook(module,args,output):
        if module.layer_idx in [0,47]:
            calls.append(dict(layer=module.layer_idx,shape=list(output.shape),time=time.time()))
            if module.layer_idx==47:log('forward_complete count='+str(sum(x['layer']==47 for x in calls)))
    handles=[b.register_forward_hook(hook) for b in pipe.transformer.blocks]
    kwargs=dict(prompt=prompt,image_tensor=pixel,cond_latent=cond,prompt_embeds=pe,prompt_mask=pm,
       negative_prompt_embeds=ne,negative_prompt_mask=nm,height=480,width=832,num_frames=121,
       guidance_scale=3.0,shift=3.0,output_type='latent',batch_cfg=False)

    import copy
    predictions=[]
    class BoundaryDone(Exception):pass
    def tensor_file(name,t):
        x=t.detach().cpu().contiguous()
        torch.save(x,ROOT/(name+'.pt'))
        return dict(file=name+'.pt',shape=list(x.shape),dtype=str(x.dtype),sha256_raw=hashlib.sha256(x.view(torch.uint8).numpy().tobytes()).hexdigest())
    binding=dict(reference_injection=['cached original conditions and encoder RNG','full 48-layer GPU transformer cond/uncond outputs injected into CPU boundary replay','original GPU scheduler input latent/state injected into CPU replay'],target_GPU_count=0,new_external_GPU_forwards=2,scope='first step of original 40-step schedule only',source_pipeline=str(ASSET/'source/lingbot_video/pipeline_lingbot_video.py'))
    write('BOUNDARY_PROTOCOL.json',binding)
    def pred_hook(module,args,output):
        x=output[0].detach().float()
        branch='cond' if not predictions else 'uncond'
        tensor_file(branch+'_prediction',x)
        predictions.append(x.cpu())
    ph=pipe.transformer.register_forward_hook(pred_hook)
    original_step=pipe.scheduler.step
    original_paint=pipe._apply_inpainting
    boundary={}
    def step(model_output,timestep,sample,*args,**kw):
        assert len(predictions)==2
        state=copy.deepcopy(pipe.scheduler)
        for name,value in vars(state).items():
            if isinstance(value,torch.Tensor):setattr(state,name,value.cpu())
        tensor_file('scheduler_input_latent',sample)
        tensor_file('scheduler_model_output_GPU',model_output)
        tensor_file('timestep',timestep)
        torch.save(state,ROOT/'scheduler_state_before.pt')
        merged=predictions[1]+3.0*(predictions[0]-predictions[1])
        tensor_file('cfg_merged_CPU',merged)
        gpu_model=model_output.detach().cpu()
        boundary['cfg_bits_equal']=torch.equal(merged.view(torch.int32),gpu_model.view(torch.int32))
        result=original_step(model_output,timestep,sample,*args,**kw)
        tensor_file('scheduler_output_GPU',result[0])
        cpu_kw=dict(kw);cpu_kw['generator']=None
        cpu_result=type(state).step(state,merged,timestep.cpu(),sample.cpu(),*args,**cpu_kw)[0]
        tensor_file('scheduler_output_CPU',cpu_result)
        boundary['scheduler_bits_equal']=torch.equal(cpu_result.view(torch.int32),result[0].cpu().view(torch.int32))
        boundary['cpu_scheduler_output']=cpu_result
        boundary['scheduler_class']=type(state).__name__
        boundary['timesteps']=pipe.scheduler.timesteps.cpu().tolist()
        boundary['scheduler_source']=__import__('inspect').getfile(type(state))
        return result
    pipe.scheduler.step=step
    def paint(latents,conditioning):
        result=original_paint(latents,conditioning)
        if 'cpu_scheduler_output' in boundary:
            cpu_result=original_paint(boundary.pop('cpu_scheduler_output'),conditioning.cpu())
            tensor_file('next_latent_GPU',result)
            tensor_file('next_latent_CPU',cpu_result)
            tensor_file('cond_latent_injection',conditioning)
            boundary['next_latent_bits_equal']=torch.equal(cpu_result.view(torch.int32),result.cpu().view(torch.int32))
            boundary['state']='PASS_LIMITED_CFG_SCHEDULER_NEXT_LATENT' if all(boundary[k] for k in ('cfg_bits_equal','scheduler_bits_equal','next_latent_bits_equal')) else 'FAIL_NUMERIC_BOUNDARY'
            write('BOUNDARY_AUDIT.json',boundary)
            raise BoundaryDone()
        tensor_file('initial_latent_after_inpainting',result)
        return result
    pipe._apply_inpainting=paint
    generator=torch.Generator(device='cuda');generator.set_state(rng_after_encode)
    try:
        with torch.no_grad():pipe(**kwargs,num_inference_steps=40,generator=generator)
    except BoundaryDone:
        assert json.loads((ROOT/'BOUNDARY_AUDIT.json').read_text())['state'].startswith('PASS')
    else:
        raise RuntimeError('first-step stop boundary not reached')
    ph.remove()
    write('STATUS.json',dict(state='PASS_LIMITED_CFG_SCHEDULER_NEXT_LATENT',target_GPU_count=0,external_GPU_forwards=len(predictions),elapsed=time.time()-started,full_video=False))
except BaseException:
    write('FAILURE.json',dict(error=traceback.format_exc(),elapsed=time.time()-started))
    write('STATUS.json',dict(state='STOPPED_FAILURE_PRESERVED'))
    raise
