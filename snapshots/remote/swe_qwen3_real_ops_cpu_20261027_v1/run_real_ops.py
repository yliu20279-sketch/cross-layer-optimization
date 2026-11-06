"""Bounded checkpoint-backed CPU subchains; no GPU, agent or simulator."""
import hashlib,json,sys,time,traceback
from pathlib import Path
from types import SimpleNamespace
import torch
import torch.nn.functional as F
from safetensors import safe_open
torch.set_num_threads(1);torch.set_num_interop_threads(1)
B=Path('/mnt/sda1/h3240101068');R=Path(__file__).resolve().parent;O=R/'attempt1';O.mkdir(exist_ok=False)
A=B/'swe_qwen3_bf16_functional_v1_20261026';sys.path.insert(0,str(A))
from bf16_adapter import BF16Adapter,NativeCodec,AppendOnlyKV
from test_adapter import load_source,config,freeze
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  while b:=f.read(8*1024*1024):h.update(b)
 return h.hexdigest()
P=json.loads((R/'PROTOCOL.json').read_text());env,ast_hash=load_source(A/'modeling_qwen3_moe.py')
MODEL=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B')
idx=json.loads((MODEL/'model.safetensors.index.json').read_text())['weight_map']
cfgdata=json.loads((MODEL/'config.json').read_text());cfg=config(True);cfg.rms_norm_eps=cfgdata['rms_norm_eps'];cfg.rope_theta=cfgdata['rope_theta']
adapter=BF16Adapter(NativeCodec(A/'libbf16_codec_bridge.so'));weights={};weight_records={};checks=[];ties=[];normdiag=[]
def weight(suffix):
 key='model.layers.0.'+suffix
 if key not in weights:
  with safe_open(str(MODEL/idx[key]),framework='pt',device='cpu') as f:weights[key]=f.get_tensor(key)
  x=weights[key];assert x.dtype==torch.bfloat16
  weight_records[key]=dict(shard=idx[key],shape=list(x.shape),dtype=str(x.dtype),tensor_sha256=hashlib.sha256(x.contiguous().view(torch.uint8).numpy().tobytes()).hexdigest())
 return weights[key]
def compare(name,x,y,**kw):
 d=(x.float()-y.float()).abs()
 checks.append(dict(name=name,exact=bool(torch.equal(x,y)),shape=list(x.shape),unequal=int((x!=y).sum()),max_abs=float(d.max()),finite=bool(torch.isfinite(x).all()),**kw))
def norm_source(x,w):
 m=freeze(env['Qwen3MoeRMSNorm'](x.shape[-1],eps=cfg.rms_norm_eps));m.weight.copy_(w);return m(x)
def save(state,error=None):
 result=dict(state=state,error=error,protocol_sha256=sha(R/'PROTOCOL.json'),checks=checks,topk_diagnostics=ties,norm_diagnostics=normdiag,
  source_ast=ast_hash,weights=weight_records,torch=torch.__version__,threads=torch.get_num_threads(),cuda_initialized=torch.cuda.is_initialized(),NPU_runs=0,cycles=None,
  scope='CPU source-semantic comparison on checkpoint-backed real fixtures, not target instruction/communication execution')
 (O/'RESULTS.json').write_text(json.dumps(result,indent=2))
 (O/'FUNCTIONAL_EVENTS.json').write_text(json.dumps(adapter.events,indent=2))
started=time.monotonic()
try:
 with torch.inference_mode():
  for selected in P['selection']:
   p=B/selected['root']/'requests'/selected['request'];label=selected['root'];fs=torch.load(p/'layer0_actual_fixtures.pt',weights_only=True,map_location='cpu')
   manifest=json.loads((p/'MANIFEST.json').read_text())
   for item in manifest:
    if item['path'] in ['REQUEST.json','layer0_actual_fixtures.pt','actual_routes.pt']:assert sha(p/item['path'])==item['sha256']
   phases=[]
   for phase,f in fs.items():
    if phase=='prefill_chunks':phases.extend((phase+'/'+k,v) for k,v in sorted(f.items(),key=lambda x:int(x[0])))
    else:phases.append((phase,f))
   acache=AppendOnlyKV()
   class SourceCache:
    def __init__(self):self.key=None;self.value=None
    def update(self,k,v,layer,kw):
     self.key=k.clone() if self.key is None else torch.cat((self.key,k),-2)
     self.value=v.clone() if self.value is None else torch.cat((self.value,v),-2)
     return self.key,self.value
   scache=SourceCache()
   attn=freeze(env['Qwen3MoeAttention'](cfg,layer_idx=0))
   for k,param in attn.named_parameters():param.copy_(weight('self_attn.'+k))
   rope=env['Qwen3MoeRotaryEmbedding'](cfg)
   for phase,f in phases:
    context=dict(root=label,phase=phase);x=f['decoder_input'];res=adapter.add(x,f['attention_output']);w=weight('post_attention_layernorm.weight')
    an=adapter.rmsnorm(res,w);sn=norm_source(res,w);gold=f['moe_input'].reshape_as(an)
    compare('residual_norm_adapter_vs_source_CPU',an,sn,**context);compare('residual_norm_vs_captured_GPU',an,gold,**context)
    if not torch.equal(an,gold):
     ideal=res.double();variance=ideal.pow(2).mean(-1,keepdim=True);ideal=(ideal*torch.rsqrt(variance+cfg.rms_norm_eps)).to(torch.bfloat16);ideal=(ideal*w).to(torch.bfloat16)
     compare('FP64_norm_diagnostic_vs_GPU_not_alternative_implementation',ideal,gold,**context)
     normdiag.append(dict(**context,differing_tokens=torch.where((an!=gold).any(-1))[1].unique().tolist(),
      cpu_source_exact=torch.equal(an,sn),cause='GPU residual/norm intermediate not captured; FP32 reduction/rsqrt and residual boundary not independently observable'))
    logits=f['router_logits'];prob=adapter.softmax_fp32(logits);val,ids=adapter.topk(prob,8);rw=adapter.cast(val/val.sum(-1,keepdim=True),torch.bfloat16)
    actual=f['actual_selected_experts'];sorted_logits=torch.sort(logits.float(),descending=True).values
    boundary=sorted_logits[:,7]==sorted_logits[:,8];internal=(sorted_logits[:,:7]==sorted_logits[:,1:8]).any(-1)
    mismatch=(ids!=actual).any(-1);setmismatch=torch.sort(ids).values.ne(torch.sort(actual).values).any(-1)
    none=~(boundary|internal)
    ties.append(dict(**context,tokens=ids.shape[0],non_tied_rows=int(none.sum()),non_tied_id_mismatches=int((mismatch&none).sum()),
     internal_tie_rows=int(internal.sum()),boundary_tie_rows=int(boundary.sum()),id_mismatch_rows=int(mismatch.sum()),set_mismatch_rows=int(setmismatch.sum()),
     set_mismatch_without_boundary_tie=int((setmismatch&~boundary).sum()),slot_weights_exact=torch.equal(rw,f['actual_final_weights']),
     all_gpu_selected_above_or_at_CPU_kth=bool((torch.gather(logits.float(),1,actual)>=sorted_logits[:,7:8]).all())))
    ar=adapter.route(f['moe_input'],weight('mlp.gate.weight'));obj=SimpleNamespace(gate=lambda h:F.linear(h,weight('mlp.gate.weight')),top_k=8,norm_topk_prob=True)
    sl,sw,si=env['source_router_prefix'](obj,f['moe_input'].reshape(1,-1,2048))
    compare('router_GEMM_adapter_vs_source_CPU',ar['logits'],sl,**context);compare('router_GEMM_vs_captured_GPU',ar['logits'],logits,**context)
    compare('router_ID_adapter_vs_source_CPU',ar['selected'],si,**context);compare('router_ID_autonomous_CPU_vs_GPU',ar['selected'],actual,**context)
    pos=torch.arange(f['forward']['past_tokens'],f['forward']['past_tokens']+x.shape[1],dtype=torch.int64)
    rc,rs=adapter.rotary_tables(pos[None,:],rope.inv_freq)
    compare('RoPE_cos_vs_captured_GPU',rc,f['cos'],**context);compare('RoPE_sin_vs_captured_GPU',rs,f['sin'],**context)
    hidden=adapter.rmsnorm(x,weight('input_layernorm.weight'));shidden=norm_source(x,weight('input_layernorm.weight'))
    compare('input_norm_adapter_vs_source_CPU',hidden,shidden,**context)
    # Captured first-decode cache is the independent input for each reference.
    if 'layer0_key_cache_before' in f:
     k=f['layer0_key_cache_before'];v=f['layer0_value_cache_before'];acache.entries[(label,0)]=(k.clone(),v.clone());scache.key=k.clone();scache.value=v.clone()
    total=int(pos[-1])+1;mask=torch.full((1,1,x.shape[1],total),torch.finfo(torch.bfloat16).min,dtype=torch.bfloat16)
    mask.masked_fill_(torch.arange(total)[None,None,None,:]<=pos[None,None,:,None],0)
    aw=[weight('self_attn.'+s+'.weight') for s in ['q_proj','k_proj','v_proj','o_proj','q_norm','k_norm']]
    ay,ap=adapter.attention(hidden,aw,32,4,128,pos,f['cos'],f['sin'],mask,acache,label,0)
    sy,sp=attn(shidden,(f['cos'],f['sin']),mask,scache,cache_position=pos)
    compare('attention_adapter_vs_source_CPU',ay,sy,**context);compare('attention_prob_adapter_vs_source_CPU',ap,sp,**context)
    compare('attention_vs_captured_GPU',ay,f['attention_output'],**context)
    if label.endswith('gpu_20261026_v1') or phase=='decode':
     h=f['moe_input'];recorded=f['actual_selected_experts'];rweight=f['actual_final_weights'];ao=torch.zeros_like(h);so=torch.zeros_like(h)
     for expert in sorted(set(recorded.flatten().tolist())):
      slots,tokens=torch.where(recorded.T==expert);state=h[tokens]
      ew=[weight('mlp.experts.'+str(expert)+'.'+s+'.weight') for s in ['gate_proj','up_proj','down_proj']]
      ae=adapter.expert(state,*ew)
      se=F.linear(F.silu(F.linear(state,ew[0]))*F.linear(state,ew[1]),ew[2])
      compare('expert_adapter_vs_source_CPU',ae,se,expert=expert,**context)
      ao=adapter.index_add(ao,tokens,adapter.multiply(ae,rweight[tokens,slots,None]));so.index_add_(0,tokens,(se*rweight[tokens,slots,None]).to(torch.bfloat16))
     compare('recorded_dispatch_MoE_adapter_vs_source_CPU',ao,so,**context)
     output=adapter.add(res,ao.reshape_as(res));compare('recorded_dispatch_layer_output_vs_GPU',output,f['decoder_output'],**context)
    save('RUNNING')
 assert not torch.cuda.is_initialized()
 save('COMPLETE_CPU_REAL_SUBCHAIN_CHECKS_WITH_DIFFERENCES_RETAINED')
 print(json.dumps(dict(state='COMPLETE',checks=len(checks),exact=sum(c['exact'] for c in checks),elapsed_seconds=time.monotonic()-started,weight_keys=len(weights),NPU_runs=0)))
except Exception:
 save('FAILED_RETAINED',traceback.format_exc());raise
