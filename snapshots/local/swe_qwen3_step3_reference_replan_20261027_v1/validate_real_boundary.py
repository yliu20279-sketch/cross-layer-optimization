"""Existing BF16 adapter on real layer-0 residual/norm; structural EP16 mapping."""
import hashlib,json,sys
from pathlib import Path
import torch
from safetensors import safe_open
torch.set_num_threads(1)
B=Path('/mnt/sda1/h3240101068');O=Path(__file__).resolve().parent
A=B/'swe_qwen3_bf16_functional_v1_20261026'
sys.path.insert(0,str(A))
from bf16_adapter import BF16Adapter,NativeCodec
MODEL=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B')
index=json.loads((MODEL/'model.safetensors.index.json').read_text())['weight_map']
key='model.layers.0.post_attention_layernorm.weight';shard=MODEL/index[key]
with safe_open(str(shard),framework='pt',device='cpu') as f:scale=f.get_tensor(key)
adapter=BF16Adapter(NativeCodec(A/'libbf16_codec_bridge.so'))
checks=[];maps=[]
for name,rid in [('swe_qwen3_step3_gpu_20261026_v1','R0002'),('swe_qwen3_step3_development_20261026_v6','R0001')]:
 p=B/name/'requests'/rid
 fs=torch.load(p/'layer0_actual_fixtures.pt',map_location='cpu',weights_only=True)
 phases=[]
 for phase,f in fs.items():
  if phase=='prefill_chunks':phases.extend((phase+'/'+k,v) for k,v in f.items())
  else:phases.append((phase,f))
 for phase,f in phases:
  residual=adapter.add(f['decoder_input'],f['attention_output'])
  y=adapter.rmsnorm(residual,scale).reshape_as(f['moe_input']);gold=f['moe_input']
  checks.append(dict(root=name,request=rid,phase=phase,op='residual_add_then_post_attention_RMSNorm',
   exact=torch.equal(y,gold),max_abs=float((y.float()-gold.float()).abs().max()),unequal=int((y!=gold).sum()),elements=y.numel(),
   classification='EXACT_REAL_CPU_SUBCHAIN' if torch.equal(y,gold) else 'CROSS_BACKEND_DIFFERENCE_NOT_ACCEPTED'))
 routes=torch.load(p/'actual_routes.pt',map_location='cpu',weights_only=True)
 # Small deterministic real fragment: first prefill forward and first decode, all 48 layers.
 req=json.loads((p/'REQUEST.json').read_text());chosen={req['forwards'][0]['index']}
 chosen.update(f['index'] for f in req['forwards'] if f['phase']=='decode' and f['index']==next((x['index'] for x in req['forwards'] if x['phase']=='decode'),-1))
 for r in routes:
  if r['forward'] not in chosen:continue
  ids=r['selected_experts'].long();T=ids.shape[0];count=torch.bincount(ids.flatten(),minlength=128)
  rank_count=[int(count[rank::16].sum()) for rank in range(16)]
  assert sum(rank_count)==8*T
  traffic=[[0]*16 for _ in range(16)]
  for token,row in enumerate(ids.tolist()):
   for expert in row:traffic[token%16][expert%16]+=1
  maps.append(dict(source_root=name,request=rid,forward=r['forward'],phase=r['phase'],layer=r['layer'],tokens=T,
   assignments=8*T,expert_counts=count.tolist(),rank_assignments=rank_count,origin_to_owner_assignment_counts=traffic,
   active_expert_weight_bytes_unique=int((count>0).sum())*9437184,
   dispatch_payload_bytes_logical=8*T*2048*2,return_payload_bytes_logical=8*T*2048*2,
   remote_dispatch_payload_bytes=sum(traffic[i][j] for i in range(16) for j in range(16) if i!=j)*4096,
   metadata_and_packet_overhead='NOT_COUNTED_NOT_PHYSICAL_BYTES',
   residency='NOT_ASSUMED; unique active weights may require paging',cycles=None))
assert not torch.cuda.is_initialized()
report=dict(state='REAL_CPU_BOUNDARY_CHECK_NOT_NPU',checks=checks,weight_key=key,shard=index[key],
 adapter_sha256=hashlib.sha256((A/'bf16_adapter.py').read_bytes()).hexdigest(),
 codec_sha256=hashlib.sha256((A/'libbf16_codec_bridge.so').read_bytes()).hexdigest(),
 acceptance='exact comparison; differences retained, no retrospective tolerance',cuda_initialized=False,NPU_runs=0)
(O/'REAL_BOUNDARY_CHECK.json').write_text(json.dumps(report,indent=2))
(O/'REAL_EP16_MAPPING.json').write_text(json.dumps(dict(state='REAL_ROUTE_STRUCTURAL_MAPPING_ONLY',
 mapping='candidate EP16 owner=e%16, origin=token%16 reset per forward; TP16 attention and KV4x remain unexecuted',
 capacity='host128GiB/HB8GiB overlay; no residency/timing claim',records=maps),indent=2))
print(json.dumps(dict(checks=checks,mapped_records=len(maps),NPU_runs=0),indent=2))
