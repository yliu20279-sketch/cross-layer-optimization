"""Bounded external source attention diagnostics; no full-model execution."""
import os
os.environ['CUDA_VISIBLE_DEVICES']='1';os.environ['DIFFUSERS_ATTN_BACKEND']='_native_flash'
import torch,pathlib,json,sys,time,gc,hashlib
from safetensors import safe_open
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');G=P.parent/'lingbot_step3_capture_20261028_v1';A=pathlib.Path('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe');D=P/'external_attention_attempt1';D.mkdir(exist_ok=False)
sys.path.insert(0,str(A/'source'));import lingbot_video.transformer_lingbot_video as src
torch.set_num_threads(1);torch.set_grad_enabled(False);torch.backends.cuda.matmul.allow_tf32=False
refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'];state={}
for file in sorted({r['canonical_file'] for r in refs}):
 with safe_open(file,framework='pt',device='cpu') as f:
  for r in refs:
   key=r['name'][len('blocks.0.'):]
   if r['canonical_file']==file and (key.startswith('attn.') or key in ['norm1.weight','scale_shift_table']):state[key]=f.get_tensor(r['name'])
with torch.device('meta'):attn=src.LingBotVideoAttention(2048,16,1e-6,'attn.to_q.bias' in state,'attn.to_out.bias' in state)
attn.load_state_dict({k[5:]:v for k,v in state.items() if k.startswith('attn.')},assign=True);attn=attn.cuda().eval()
norm=src.LingBotVideoRMSNorm(2048,1e-6).cuda();norm.weight=torch.nn.Parameter(state['norm1.weight'].cuda(),requires_grad=False)
rows=[];start=time.time();branch=''
def save(name,t):torch.save(t.detach().cpu(),D/(branch+'_'+name+'.pt'))
for name in ['to_q','to_k','to_v','norm_q','norm_k']:
 getattr(attn,name).register_forward_hook(lambda m,i,o,n=name:save(n,o))
original=src.dispatch_attention_fn

def dispatch(q,k,v,*a,**kw):
 save('rope_q',q);save('rope_k',k)
 with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA],record_shapes=True) as prof:
  out=original(q,k,v,*a,**kw);torch.cuda.synchronize()
 prof.export_chrome_trace(str(D/(branch+'_trace.json')));save('core',out);return out
src.dispatch_attention_fn=dispatch
for branch in ['cond','uncond']:
 x=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_block_input.pt'),weights_only=True).cuda();temb=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_temb6_constant_row.pt'),weights_only=True).cuda();freq=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_rotary.pt'),weights_only=True).cuda()
 mod=(temb+state['scale_shift_table'].cuda()).chunk(6,-1);z=norm(x);save('norm1',z);inp=(z*(1+mod[1])+mod[0]).to(torch.bfloat16);save('input',inp)
 with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA],record_shapes=True) as prof:
  # dispatcher has its own profiler, so profile projections separately by hooks only.
  pass
 out=attn(inp,freq);save('output',out);gold=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_attention_output.pt'),weights_only=True)
 bad=int((out.cpu().view(torch.int16)!=gold.view(torch.int16)).sum());r=dict(branch=branch,shape=list(out.shape),BF16_output_bit_mismatches=bad);rows.append(r);print(json.dumps(r),flush=True);assert bad==0
 del x,temb,freq,z,inp,out,gold;gc.collect();torch.cuda.empty_cache()
 assert torch.cuda.max_memory_allocated()<6*2**30
manifest=[dict(file=str(q.relative_to(D)),bytes=q.stat().st_size,sha256=hashlib.file_digest(q.open('rb'),'sha256').hexdigest()) for q in sorted(D.glob('*.pt'))]
(D/'MANIFEST.json').write_text(json.dumps(manifest,indent=2));(D/'RESULT.json').write_text(json.dumps(dict(status='PASS_LIMITED_SOURCE_FULL_ATTENTION_REBINDING',rows=rows,wall_seconds=time.time()-start,peak_GPU_bytes=torch.cuda.max_memory_allocated(),target_GPU_count=0,external_reference_jobs=1,full_model_calls=0),indent=2))
