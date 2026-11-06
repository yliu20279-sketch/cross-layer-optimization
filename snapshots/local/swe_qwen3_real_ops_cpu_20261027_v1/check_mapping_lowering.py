"""CPU functional evaluation of candidate vector lowering and EP16 return order."""
import ctypes,hashlib,json,sys
from pathlib import Path
import torch
from safetensors import safe_open
torch.set_num_threads(1)
B=Path('/mnt/sda1/h3240101068');R=Path(__file__).resolve().parent;O=R/'mapping_attempt1';O.mkdir(exist_ok=False)
A=B/'swe_qwen3_bf16_functional_v1_20261026';sys.path.insert(0,str(A))
from bf16_adapter import BF16Adapter,NativeCodec
a=BF16Adapter(NativeCodec(A/'libbf16_codec_bridge.so'))
MODEL=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B')
idx=json.loads((MODEL/'model.safetensors.index.json').read_text())['weight_map'];cache={}
def w(suffix):
 k='model.layers.0.'+suffix
 if k not in cache:
  with safe_open(str(MODEL/idx[k]),framework='pt',device='cpu') as f:cache[k]=f.get_tensor(k)
 return cache[k]
lib=ctypes.CDLL(str(R/'libbf16_vector_bridge.so'));lib.swe_vector_linear.argtypes=[ctypes.c_void_p]*3+[ctypes.c_size_t]*3
checks=[];ledgers=[]
def comp(name,x,y,phase):checks.append(dict(name=name,phase=phase,exact=torch.equal(x,y),unequal=int((x!=y).sum()),max_abs=float((x.float()-y.float()).abs().max())))
fs=torch.load(B/'swe_qwen3_step3_gpu_20261026_v1/requests/R0002/layer0_actual_fixtures.pt',weights_only=True,map_location='cpu')
for phase,f in fs.items():
 h=f['moe_input'].contiguous();gate=w('mlp.gate.weight').contiguous();M,K=h.shape;N=gate.shape[0];out=torch.empty((M,N),dtype=torch.bfloat16)
 lib.swe_vector_linear(h.data_ptr(),gate.data_ptr(),out.data_ptr(),M,N,K)
 comp('sequential_FP32_vector_lowering_vs_GPU_router_logits',out,f['router_logits'],phase)
 comp('sequential_FP32_vector_lowering_vs_CPU_adapter',out,a.linear(h,gate),phase)
 # Counts are primitive arithmetic work, not issued instructions or cycles.
 ledgers.append(dict(phase=phase,M=M,N=N,K=K,FP32_mul=M*N*K,FP32_add=M*N*K,
  BF16_decode_scalar_calls=2*M*N*K,BF16_encode_scalar_calls=M*N,
  tile=dict(m=1,n=64,k=64),tile_SRAM_payload_bytes=1*64*2+64*64*2+1*64*4,
  SRAM_scope='single tile only; not full layer peak or bank arbitration',cycles=None))
 ids=f['actual_selected_experts'];weights=f['actual_final_weights'];contrib=[];canonical=torch.zeros_like(h)
 for expert in sorted(set(ids.flatten().tolist())):
  slots,tokens=torch.where(ids.T==expert)
  # Split dispatch by token origin, reconstruct source order before expert kernel.
  sequence=list(zip(tokens.tolist(),slots.tolist()))
  assigned=[(j,t,s) for j,(t,s) in enumerate(sequence)]
  routed=[v for origin in range(16) for v in assigned if v[1]%16==origin]
  restored=sorted(routed,key=lambda v:v[0]);assert [(t,s) for _,t,s in restored]==sequence
  result=a.expert(h[tokens],*[w('mlp.experts.'+str(expert)+'.'+p+'.weight') for p in ['gate_proj','up_proj','down_proj']])
  weighted=a.multiply(result,weights[tokens,slots,None]);canonical=a.index_add(canonical,tokens,weighted)
  contrib.append((expert,expert%16,tokens,weighted))
 # Return may arrive in rank order; origin waits and commits in source expert order.
 arrival=sorted(contrib,key=lambda v:(v[1],v[0]));preserved=torch.zeros_like(h);rank_order=torch.zeros_like(h)
 for expert,rank,tokens,weighted in arrival:rank_order=a.index_add(rank_order,tokens,weighted)
 for expert,rank,tokens,weighted in sorted(arrival,key=lambda v:v[0]):preserved=a.index_add(preserved,tokens,weighted)
 comp('EP16_return_source_order_vs_canonical',preserved,canonical,phase)
 comp('EP16_naive_rank_order_vs_canonical_diagnostic',rank_order,canonical,phase)
report=dict(state='CANDIDATE_SOFTWARE_LOWERING_AND_EP16_CPU_FUNCTIONAL_CHECK',checks=checks,primitive_ledgers=ledgers,
 code_sha256=hashlib.sha256((R/'bf16_vector_bridge.cpp').read_bytes()).hexdigest(),library_sha256=hashlib.sha256((R/'libbf16_vector_bridge.so').read_bytes()).hexdigest(),
 cuda_initialized=torch.cuda.is_initialized(),NPU_runs=0,
 scope='host FP32 software candidate; no NPUSim events, target ISA instruction mapping, SRAM lifetime or target timing certification')
assert not torch.cuda.is_initialized()
(O/'RESULTS.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
