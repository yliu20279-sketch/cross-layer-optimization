"""CPU selected-row block with all independently generated context K/V."""
import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='16'
import pathlib,json,sys,time,ctypes,numpy as np,torch
from safetensors import safe_open
from guarded_adapter import rms,linear,rb
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');G=P.parent/'lingbot_step3_capture_20261028_v1';V2=P.parent/'lingbot_step4_router_repair_20261028_v2';sys.path.insert(0,str(V2));from router_contract import select
torch.set_num_threads(4);torch.set_grad_enabled(False)
assert json.loads((P/'FULL_KV_RESULT.json').read_text())['status']=='PASS_LIMITED_FULL_CONTEXT_KV'
assert json.loads((P/'FLASH_DIAGNOSTIC_V3_RESULT.json').read_text())['status']=='PASS_LIMITED_CORE_ISOLATED'
D=P/'ffn_failure_diagnostic_v1';D.mkdir(exist_ok=False);start=time.time();state={};refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references']
for file in sorted({r['canonical_file'] for r in refs}):
 with safe_open(file,framework='pt',device='cpu') as f:
  for r in refs:
   if r['canonical_file']==file:state[r['name'][len('blocks.0.'):]]=f.get_tensor(r['name'])
math=ctypes.CDLL(str(P/'libprofile_math.so'));math.profile_math_open.argtypes=[ctypes.c_char_p];assert math.profile_math_open(str(P/'sfu_profile').encode())==0
for fn in ['profile_silu','profile_sigmoid']:getattr(math,fn).argtypes=[ctypes.c_void_p]*2+[ctypes.c_size_t]
router=ctypes.CDLL(str(P/'librouter_split_strided.so'));router.split.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int]*5
rope=ctypes.CDLL(str(P/'librope_cpu.so'));rope.rope_cpu.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int]*2
flash=ctypes.CDLL(str(P/'libflash_cpu_simd.so'));flash.flash_cpu.argtypes=[ctypes.c_void_p]*4+[ctypes.c_int]*2+[ctypes.c_void_p]*2+[ctypes.c_int]
ex=np.memmap(P/'sfu_profile/ex2_all_f32.raw',dtype=np.uint32,mode='r');rows=[]
def w(n):return state[n].float().numpy()
def fixture(branch,n):return torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_'+n+'.pt'),weights_only=True)
def compare(branch,n,x,g):
 a=g.float().numpy();r=dict(branch=branch,stage=n,elements=x.size,BF16_bit_mismatches=int((x.view(np.uint32)!=a.view(np.uint32)).sum()),max_abs=float(np.abs(x-a).max()));rows.append(r);np.save(D/(branch+'_'+n+'.npy'),x);print(json.dumps(r),flush=True)
def apply_rope(x,f):
 y=np.empty_like(x);assert rope.rope_cpu(x.ctypes.data,np.ascontiguousarray(f).ctypes.data,y.ctypes.data,len(x),2)==0;return rb(y)
def free_router(x):
 x=np.ascontiguousarray(x);weight=w('ffn.router.weight');a=np.empty((5,len(x),128),dtype=np.float32);assert router.split(x.ctypes.data,weight.ctypes.data,a.ctypes.data,len(x),128,2048,5,8)==0;y=a[0]+a[1]
 for p in range(2,5):y=y+a[p]
 scores=np.empty_like(y);assert math.profile_sigmoid(y.ctypes.data,scores.ctypes.data,y.size)==0
 ids,weights,_=select(torch.from_numpy(scores),state['ffn.router.e_score_correction_bias']);return ids.numpy(),weights.float().numpy()
def mlp(x,w1,w3,w2):
 gate=linear(x,w1);up=linear(x,w3);act=np.empty_like(gate);assert math.profile_silu(gate.ctypes.data,act.ctypes.data,gate.size)==0;return linear(rb(rb(act)*up),w2)
branch='cond';begin=11776;end=11840;idx=np.arange(begin,end);M=64
x=np.load(P/'full_query_acceptance/cond_11776/ffn_input.npy');gold=fixture(branch,'ffn_input')[0,idx].float().numpy();assert np.array_equal(x.view(np.uint32),gold.view(np.uint32));ids,weights=free_router(x);gi=torch.load(P/'free_router_validation/cond_ids.pt',weights_only=True).numpy()[idx];gw=torch.load(P/'free_router_validation/cond_weights.pt',weights_only=True).float().numpy()[idx];assert np.array_equal(ids,gi) and np.array_equal(weights.view(np.uint32),gw.view(np.uint32));np.save(D/'ids.npy',ids);np.save(D/'weights.npy',weights)
def staged_mlp(name,x,w1,w3,w2):
 gate=linear(x,w1);up=linear(x,w3);act=np.empty_like(gate);assert math.profile_silu(gate.ctypes.data,act.ctypes.data,gate.size)==0;act=rb(act);product=rb(act*up);out=linear(product,w2)
 for label,a in [('gate',gate),('up',up),('act',act),('product',product),('out',out)]:np.save(D/(name+'_'+label+'.npy'),a)
 return out
shared=staged_mlp('shared',x,w('ffn.shared_experts.gate_proj.weight'),w('ffn.shared_experts.up_proj.weight'),w('ffn.shared_experts.down_proj.weight'));sg=fixture(branch,'shared_output')[0,idx].float().numpy();np.save(D/'shared_Golden.npy',sg)
slots=np.zeros((512,2048),dtype=np.float32);flat=ids.reshape(-1)
for e in range(128):
 pos=np.where(flat==e)[0]
 if len(pos):slots[pos]=staged_mlp('expert'+str(e),x[pos//8],state['ffn.experts.w1'][e].float().numpy(),state['ffn.experts.w3'][e].float().numpy(),state['ffn.experts.w2'][e].float().numpy())
prod=slots.reshape(64,8,2048)*weights[:,:,None];streams=[(np.float32(0)+prod[:,i])+prod[:,i+4] for i in range(4)];routed=rb(((streams[0]+streams[1])+streams[2])+streams[3]);out=rb(routed+shared);gold=fixture(branch,'ffn_output')[0,idx].float().numpy();old=np.load(P/'full_query_acceptance/cond_11776/ffn_output.npy');assert np.array_equal(old,out)
for label,a in [('slots',slots),('routed',routed),('output',out),('Golden',gold)]:np.save(D/(label+'.npy'),a)
r=dict(status='FAILURE_REPRODUCED_CPU_ONLY',shared_bit_mismatches=int((shared.view(np.uint32)!=sg.view(np.uint32)).sum()),shared_positions=np.argwhere(shared.view(np.uint32)!=sg.view(np.uint32)).tolist(),FFN_bit_mismatches=int((out.view(np.uint32)!=gold.view(np.uint32)).sum()),positions=np.argwhere(out.view(np.uint32)!=gold.view(np.uint32)).tolist(),router_slots_weights_match=True,target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized());(P/'FFN_FAILURE_DIAGNOSTIC.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
