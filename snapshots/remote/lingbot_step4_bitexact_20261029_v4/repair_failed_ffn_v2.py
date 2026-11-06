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
D=P/'ffn_failure_repair_v2';D.mkdir(exist_ok=False);start=time.time();state={};refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references']
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
from batch_adapter import expert_linear
C=P/'ffn_failure_diagnostic_v1';x=np.load(P/'full_query_acceptance/cond_11776/ffn_input.npy');ids,weights=free_router(x);flat=ids.reshape(-1);slots=np.load(C/'slots.npy').copy();full_ids=torch.load(P/'free_router_validation/cond_ids.pt',weights_only=True).numpy();src=np.where(full_ids.reshape(-1)==28)[0];full=fixture('cond','ffn_input')[0,torch.from_numpy(src//8)].float().numpy();gate=expert_linear(full,state['ffn.experts.w1'][28].float().numpy());up=expert_linear(full,state['ffn.experts.w3'][28].float().numpy());act=np.empty_like(gate);assert math.profile_silu(gate.ctypes.data,act.ctypes.data,gate.size)==0;product=rb(rb(act)*up);out=expert_linear(product,state['ffn.experts.w2'][28].float().numpy());pos=np.where(flat==28)[0];lookup=np.searchsorted(src//8,pos//8+11776);assert np.array_equal(src[lookup]//8,pos//8+11776);slots[pos]=out[lookup];prod=slots.reshape(64,8,2048)*weights[:,:,None];streams=[(np.float32(0)+prod[:,i])+prod[:,i+4] for i in range(4)];routed=rb(((streams[0]+streams[1])+streams[2])+streams[3]);shared=np.load(C/'shared_out.npy');fo=rb(routed+shared);gold=fixture('cond','ffn_output')[0,11776:11840].float().numpy();np.save(D/'output.npy',fo);np.save(D/'expert28_full_output.npy',out)
r=dict(status='PASS_LIMITED_ISOLATED_FAILED_FFN_REPAIR' if np.array_equal(fo.view(np.uint32),gold.view(np.uint32)) else 'PARTIAL_FFN_REPAIR',elements=fo.size,old_bit_mismatches=4,new_bit_mismatches=int((fo.view(np.uint32)!=gold.view(np.uint32)).sum()),target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized(),scope='isolated FFN on proven original input, expert28 full148 batch; not autonomous whole layer',old_failure_preserved=True);(P/'FFN_REPAIR_V2_RESULT.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
