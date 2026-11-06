"""Full layer0 real-checkpoint CPU source comparison; autonomous CPU router."""
import hashlib,inspect,json,sys
from pathlib import Path
import torch
from safetensors import safe_open
from transformers import Qwen3MoeConfig
from transformers.cache_utils import DynamicCache
import transformers.models.qwen3_moe.modeling_qwen3_moe as source
torch.set_num_threads(1);torch.set_num_interop_threads(1)
R=Path(__file__).resolve().parent;O=R/'layer_attempt1';O.mkdir(exist_ok=False)
B=Path('/mnt/sda1/h3240101068');A=B/'swe_qwen3_bf16_functional_v1_20261026';sys.path.insert(0,str(A))
from bf16_adapter import BF16Adapter,NativeCodec,AppendOnlyKV
sourcepath=Path(inspect.getsourcefile(source));assert hashlib.sha256(sourcepath.read_bytes()).hexdigest()=='3af43d01f9f902c8009b6dd7d7b8b563561b53dd0aa54175f585ae90d049fdb8'
MODEL=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');cfg=Qwen3MoeConfig.from_pretrained(MODEL,local_files_only=True);cfg._attn_implementation='eager'
idx=json.loads((MODEL/'model.safetensors.index.json').read_text())['weight_map'];state={}
for key,shard in idx.items():
 if key.startswith('model.layers.0.'):
  with safe_open(str(MODEL/shard),framework='pt',device='cpu') as f:state[key[len('model.layers.0.'):]]=f.get_tensor(key)
assert len(state)==393 and all(t.dtype==torch.bfloat16 for t in state.values())
with torch.device('meta'):layer=source.Qwen3MoeDecoderLayer(cfg,0)
layer.load_state_dict(state,assign=True,strict=True);layer.eval().requires_grad_(False)
a=BF16Adapter(NativeCodec(A/'libbf16_codec_bridge.so'));ac=AppendOnlyKV();sc=DynamicCache();checks=[]
def cmp(name,x,y,phase):checks.append(dict(name=name,phase=phase,exact=torch.equal(x,y),unequal=int((x!=y).sum()),max_abs=float((x.float()-y.float()).abs().max())))
fs=torch.load(B/'swe_qwen3_step3_gpu_20261026_v1/requests/R0002/layer0_actual_fixtures.pt',weights_only=True,map_location='cpu')
ew=[tuple(state['mlp.experts.'+str(e)+'.'+n+'.weight'] for n in ['gate_proj','up_proj','down_proj']) for e in range(128)]
aw=[state['self_attn.'+n+'.weight'] for n in ['q_proj','k_proj','v_proj','o_proj','q_norm','k_norm']]
with torch.inference_mode():
 for phase,f in fs.items():
  x=f['decoder_input'];past=f['forward']['past_tokens'];pos=torch.arange(past,past+x.shape[1],dtype=torch.int64)
  mask=torch.full((1,1,x.shape[1],int(pos[-1])+1),torch.finfo(torch.bfloat16).min,dtype=torch.bfloat16)
  mask.masked_fill_(torch.arange(int(pos[-1])+1)[None,None,None,:]<=pos[None,None,:,None],0)
  h=a.rmsnorm(x,state['input_layernorm.weight'],cfg.rms_norm_eps)
  attention,_=a.attention(h,aw,32,4,128,pos,f['cos'],f['sin'],mask,ac,'short',0)
  residual=a.add(x,attention);h=a.rmsnorm(residual,state['post_attention_layernorm.weight'],cfg.rms_norm_eps)
  moe,route=a.moe(h,state['mlp.gate.weight'],ew,8);y=a.add(residual,moe)
  sy=layer(x,attention_mask=mask,past_key_value=sc,use_cache=True,cache_position=pos,position_embeddings=(f['cos'],f['sin']))[0]
  cmp('full_layer_adapter_vs_unmodified_source_CPU',y,sy,phase)
  cmp('full_layer_autonomous_CPU_vs_captured_GPU',y,f['decoder_output'],phase)
  cmp('autonomous_route_CPU_vs_captured_GPU',route['selected'],f['actual_selected_experts'],phase)
  cmp('KV_key_adapter_vs_source_CPU',ac.entries[('short',0)][0],sc.key_cache[0],phase)
  cmp('KV_value_adapter_vs_source_CPU',ac.entries[('short',0)][1],sc.value_cache[0],phase)
assert not torch.cuda.is_initialized()
result=dict(state='FULL_LAYER0_CPU_SOURCE_CHECK_WITH_CROSS_BACKEND_DIFFERENCES_RETAINED',checks=checks,
 source_sha256=hashlib.sha256(sourcepath.read_bytes()).hexdigest(),weight_keys=len(state),parameter_elements=sum(t.numel() for t in state.values()),
 router='autonomous CPU logits and Top8; no injected recorded dispatch',cos_sin='captured same GPU fixture used as common layer input',
 scope='one real layer0 prefill and cached decode on CPU; not layer1, complete model, GPU exact, target NPU or timing',NPU_runs=0,cuda_initialized=False)
(O/'RESULTS.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
