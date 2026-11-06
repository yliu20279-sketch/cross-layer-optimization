import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import hashlib,inspect,json,sys
from pathlib import Path
import numpy as np
import torch
from safetensors import safe_open
from transformers import Qwen3MoeConfig
from transformers.cache_utils import DynamicCache
import transformers.models.qwen3_moe.modeling_qwen3_moe as source
R=Path(__file__).resolve().parent;D=R/'coupled_attempt1';D.mkdir(exist_ok=False);B=R.parent
torch.set_num_threads(1);torch.set_num_interop_threads(1)
sys.path.insert(0,str(B/'swe_qwen3_bf16_functional_v1_20261026'));from bf16_adapter import BF16Adapter,NativeCodec,AppendOnlyKV
def dump(p,v):p.write_text(json.dumps(v,indent=2))
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while x:=f.read(8*1024*1024):h.update(x)
 return h.hexdigest()
def blob(t):return t.contiguous().view(torch.uint8).numpy().tobytes()
for n,h in json.loads((R/'COUPLED_FREEZE.json').read_text()).items():assert sha(R/n)==h
sp=Path(inspect.getsourcefile(source));assert sha(sp)=='3af43d01f9f902c8009b6dd7d7b8b563561b53dd0aa54175f585ae90d049fdb8'
M=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');mv={v['path']:v for v in json.loads((M.parent.parent/'MODEL_VERIFICATION.json').read_text())};idx=json.loads((M/'model.safetensors.index.json').read_text())['weight_map'];cfg=Qwen3MoeConfig.from_pretrained(M,local_files_only=True);cfg._attn_implementation='eager'
for n in ['model.safetensors.index.json','config.json']:assert sha(M/n)==mv[n]['sha256']
state=[{},{}];shards=sorted({v for k,v in idx.items() if k.startswith(('model.layers.0.','model.layers.1.'))});verified={}
for shard in shards:
 verified[shard]=sha(M/shard);assert verified[shard]==mv[shard]['sha256']
 with safe_open(str(M/shard),framework='pt',device='cpu') as f:
  for key in idx:
   for layer in [0,1]:
    prefix='model.layers.%d.'%layer
    if key.startswith(prefix) and idx[key]==shard:state[layer][key[len(prefix):]]=f.get_tensor(key)
layers=[]
for i in [0,1]:
 assert len(state[i])==393 and all(t.dtype==torch.bfloat16 for t in state[i].values())
 with torch.device('meta'):layer=source.Qwen3MoeDecoderLayer(cfg,i)
 layer.load_state_dict(state[i],assign=True,strict=True);layer.eval().requires_grad_(False);layers.append(layer)
root=B/'swe_qwen3_step3_gpu_20261026_v1/requests/R0002';fp=root/'layer0_actual_fixtures.pt';fm=json.loads((root/'MANIFEST.json').read_text());assert sha(fp)==next(v['sha256'] for v in fm if v['path']==fp.name);fixtures=torch.load(fp,weights_only=True,map_location='cpu')
from coupled_adapter import CoupledAdapter,CoupledKV
a=CoupledAdapter(NativeCodec(B/'swe_qwen3_bf16_functional_v1_20261026/libbf16_codec_bridge.so'),R/'libsource_gemm_v2.so',D);a.bind(state);ac=CoupledKV(a);sc=DynamicCache();checks=[];contracts=[]
probe=torch.zeros((1,4,1,128),dtype=torch.bfloat16)
try:ac.append('short',0,probe,probe,torch.tensor([19],dtype=torch.int64))
except ValueError:a.svc.negative.append('cached_decode_before_prefill_rejected')
else:raise AssertionError('cache accepted missing prefill')
def cmp(name,x,y,phase,layer,strict=True):
 v=dict(name=name,phase=phase,layer=layer,shape=list(x.shape),dtype=str(x.dtype),exact=torch.equal(x,y),different=int((x!=y).sum()),max_abs=float((x.float()-y.float()).abs().max()),strict=strict);checks.append(v)
 if strict:assert v['exact'],v
with torch.inference_mode():
 for phase in ['prefill','decode']:
  f=fixtures[phase];x=f['decoder_input'];sy=x.clone();pos=torch.arange(f['forward']['past_tokens'],f['forward']['past_tokens']+x.shape[1],dtype=torch.int64);mask=torch.full((1,1,x.shape[1],int(pos[-1])+1),torch.finfo(torch.bfloat16).min,dtype=torch.bfloat16);mask.masked_fill_(torch.arange(int(pos[-1])+1)[None,None,None,:]<=pos[None,None,:,None],0)
  for i in [0,1]:
   a.begin_layer(phase,i,x)
   st=state[i];start=x.clone();h=a.rmsnorm(x,st['input_layernorm.weight']);aw=[st['self_attn.'+n+'.weight'] for n in ['q_proj','k_proj','v_proj','o_proj','q_norm','k_norm']];attn,prob=a.attention(h,aw,32,4,128,pos,f['cos'],f['sin'],mask,ac,'short',i);res=a.add(x,attn);norm=a.rmsnorm(res,st['post_attention_layernorm.weight']);ew=[tuple(st['mlp.experts.%d.%s.weight'%(e,n)] for n in ['gate_proj','up_proj','down_proj']) for e in range(128)];moe,route=a.moe(norm,st['mlp.gate.weight'],ew,8);x=a.add(res,moe)
   a.end_layer(phase,i,x)
   sy=layers[i](sy,attention_mask=mask,past_key_value=sc,use_cache=True,cache_position=pos,position_embeddings=(f['cos'],f['sin']))[0]
   cmp('full_layer_adapter_vs_unmodified_source_CPU',x,sy,phase,i);cmp('KV_key_vs_source_CPU',ac.entries[('short',i)][0],sc.key_cache[i],phase,i);cmp('KV_value_vs_source_CPU',ac.entries[('short',i)][1],sc.value_cache[i],phase,i)
   if i==0:cmp('layer0_vs_captured_GPU',x,f['decoder_output'],phase,i,False);cmp('route_vs_captured_GPU',route['selected'],f['actual_selected_experts'],phase,i,False)
   for name,t in [('input',start),('input_norm',h),('attention_output',attn),('attention_probabilities',prob),('pre_MoE_residual',res),('post_attention_norm',norm),('moe_output',moe),('output',x),('router_logits',route['logits']),('router_probabilities',route['probabilities']),('route_IDs',route['selected']),('route_weights',route['weights']),('KV_key',ac.entries[('short',i)][0]),('KV_value',ac.entries[('short',i)][1])]:
    p=D/('%s_L%d_%s.bin'%(phase,i,name));p.write_bytes(blob(t));contracts.append(dict(path=p.name,phase=phase,layer=i,stage=name,shape=list(t.shape),dtype=str(t.dtype),bytes=p.stat().st_size,sha256=sha(p)))
   print('REFERENCE_COMPLETE',phase,i,flush=True)
assert not torch.cuda.is_initialized()
dump(D/'FILES.json',contracts);dump(D/'CHECKS.json',checks);dump(D/'PROVENANCE.json',dict(source=str(sp),source_sha256=sha(sp),fixture=str(fp),fixture_sha256=sha(fp),shards=verified,parameter_elements=[sum(t.numel() for t in st.values()) for st in state],weight_keys=[len(st) for st in state],layer1_golden='new CPU source reconstruction, not original GPU capture',cos_sin='same captured shared positional input supplied to both layers'))
dump(D/'RESULTS.json',dict(state='PASS_LIMITED_TWO_LAYERS_CPU_SOURCE',strict_checks=sum(v['strict'] for v in checks),strict_different=sum(v['different'] for v in checks if v['strict']),cross_GPU=[v for v in checks if not v['strict']],prefill_tokens=19,decode_tokens=1,layers=2,source_parameter_dtype='original BF16',target_native_runs=0,GPU_runs=0,scope='same CPU kernels source/adapter, not independent target arithmetic or whole model'))

summary=a.finish(ac);dump(D/'KV_EVENTS.json',ac.events);dump(D/'COUPLED_STATUS.json',dict(state='PASS_LIMITED_TWO_LAYER_NATIVE_MATRIX_HOST_FALLBACK_BRIDGE',**summary,strict_checks=sum(v['strict'] for v in checks),strict_different=sum(v['different'] for v in checks if v['strict']),prefill_tokens=19,decode_tokens=1,layers=2,new_native_fragments=1,new_GPU_Sniper_agent_runs=0,physical_NPU_runs=0,full_timing='NOT_CERTIFIED',mapping='N0 serial functional diagnostic; no TP16/EP16 collective claim',GPU_differences_retained=True,host_GiB=128,HB_GiB=8));print('COUPLED_COMPLETE',summary,flush=True)
