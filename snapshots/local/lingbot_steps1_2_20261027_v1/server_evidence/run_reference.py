"""External Golden-generation only. This GPU is NOT part of the target model."""
import os,sys,time,json,pathlib,traceback,hashlib,gc,subprocess
ROOT=pathlib.Path('/mnt/sda1/h3240101068/lingbot_steps1_2_20261027_v1')
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
    snapshot('ENCODE_CONDITIONS')
    pipe.text_encoder.to('cuda')
    pixel=pipe.preprocess_image(image,480,832).to(device='cuda',dtype=torch.float32)
    vlm_image=pipe._vlm_image(pixel)
    with torch.no_grad():
        pe,pm=pipe.encode_prompt(prompt,images=[vlm_image],device='cuda')
        ne,nm=pipe.encode_prompt(DEFAULT_NEGATIVE_PROMPT,images=[vlm_image],device='cuda')
    pipe.text_encoder.to('cpu');gc.collect();torch.cuda.empty_cache()
    pipe.vae.to('cuda')
    generator=torch.Generator(device='cuda').manual_seed(42)
    with torch.no_grad():cond=pipe.encode_image_latent(pixel,generator=generator)
    rng_after_encode=generator.get_state()
    torch.save(dict(prompt_embeds=pe.cpu(),prompt_mask=pm.cpu(),negative_embeds=ne.cpu(),negative_mask=nm.cpu(),cond_latent=cond.cpu(),rng_after_encode=rng_after_encode),ROOT/'conditions.pt')
    pe=pe.to('cuda');pm=pm.to('cuda');ne=ne.to('cuda');nm=nm.to('cuda');cond=cond.to('cuda')
    pipe.vae.to('cpu');gc.collect();torch.cuda.empty_cache()
    write('CONDITION_SHAPES.json',dict(prompt=list(pe.shape),negative=list(ne.shape),prompt_mask=list(pm.shape),negative_mask=list(nm.shape),cond_latent=list(cond.shape),video_tokens=48360,
          joint_tokens_cond=48360+pe.shape[1],joint_tokens_uncond=48360+ne.shape[1],full_frames=121,height=480,width=832))
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
    outputs={}
    for steps in [1,40]:
        snapshot('RUN_'+str(steps)+'_STEP',steps=steps)
        generator=torch.Generator(device='cuda');generator.set_state(rng_after_encode)
        torch.cuda.reset_peak_memory_stats();t=time.time();n_before=len(calls)
        with torch.no_grad():latent=pipe(**kwargs,num_inference_steps=steps,generator=generator).frames
        torch.cuda.synchronize()
        x=latent.detach().float().cpu()
        assert list(x.shape)==[1,16,31,60,104]
        assert torch.isfinite(x).all()
        torch.save(x,ROOT/('latent_'+str(steps)+'step.pt'))
        outputs[str(steps)]=dict(seconds=time.time()-t,shape=list(x.shape),finite=True,
          peak_allocated=torch.cuda.max_memory_allocated(),peak_reserved=torch.cuda.max_memory_reserved(),
          forwards=sum(z['layer']==47 for z in calls[n_before:]),scheduler_timesteps=pipe.scheduler.timesteps.cpu().tolist(),
          sha256_raw_FP32=hashlib.sha256(x.numpy().tobytes()).hexdigest())
        assert outputs[str(steps)]['forwards']==2*steps
        write('REFERENCE_RUNS.json',outputs)
        del latent
        if steps==1:log('ONE_STEP_PASS')
    for h in handles:h.remove()
    write('FORWARD_BOUNDARY_LOG.json',calls)
    pipe.transformer.to('cpu');gc.collect();torch.cuda.empty_cache()
    snapshot('VAE_DECODE_40STEP')
    pipe.vae.to('cuda')
    with torch.no_grad():frames=pipe._decode_latents(x.to('cuda'))
    arr=np.asarray(frames[0]);assert arr.shape==(121,480,832,3) and np.isfinite(arr).all()
    export_to_video(arr,str(ROOT/'reference_40step.mp4'),fps=24)
    from PIL import Image
    Image.fromarray((np.clip(arr[0],0,1)*255).round().astype('uint8')).save(ROOT/'first_output_frame.png')
    write('FINAL_REFERENCE.json',dict(status='PASS_LIMITED_EXTERNAL_GPU_REFERENCE',target_gpu_count=0,
          steps=[1,40],video_shape=list(arr.shape),latent_finite=True,refiner=False,full_pipeline_numeric_semantics='original modules; staged residency + source chunked restore/native attention variant',
          target_execution_certified=False,target_timing_certified=False,source_backend_equivalence_to_recommended_nightly='NOT_TESTED',
          total_seconds=time.time()-started,finished=time.time()))
    snapshot('COMPLETE_EXTERNAL_REFERENCE')
except BaseException:
    write('REFERENCE_FAILURE.json',dict(error=traceback.format_exc(),elapsed=time.time()-started,time=time.time()))
    snapshot('FAILED_REFERENCE')
    raise
