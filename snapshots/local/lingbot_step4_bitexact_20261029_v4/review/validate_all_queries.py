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
D=P/'full_query_acceptance';D.mkdir(exist_ok=True);start=time.time();state={};refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references']
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
ROOT=D;os.nice(10);all_records=[];started=time.time()
def digest(q):
 import hashlib
 with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def status(**kw):(ROOT/'STATUS.json').write_text(json.dumps(dict(target_GPU_count=0,host_GiB=128,HB_GiB=8,OMP_threads=16,elapsed_seconds=time.time()-started,**kw),indent=2))
def checkstage(branch,label,candidate,reference):
 a=reference.float().numpy();r=dict(branch=branch,stage=label,begin=begin,end=end,elements=candidate.size,BF16_bit_mismatches=int((candidate.view(np.uint32)!=a.view(np.uint32)).sum()),max_abs=float(np.abs(candidate-a).max()));np.save(D/(label+'.npy'),candidate);chunk_rows.append(r)
 if r['BF16_bit_mismatches']:
  (D/'FAILED_STAGE.json').write_text(json.dumps(r,indent=2));status(state='STOPPED_NUMERICAL_DIFFERENCE',branch=branch,begin=begin,end=end,failed_stage=label,bit_mismatches=r['BF16_bit_mismatches']);print(json.dumps(r),flush=True);raise SystemExit(2)
for branch in ['cond','uncond']:
 x=fixture(branch,'block_input')[0].float().numpy();S=len(x);temb=fixture(branch,'temb6_constant_row').float();mod=(temb+state['scale_shift_table']).chunk(6,-1);shift,scale,gate,sh2,sc2,ga2=[a.numpy() for a in [mod[0],1+mod[1],mod[2].tanh(),mod[3],1+mod[4],mod[5].tanh()]]
 inp=rb(rms(x,w('norm1.weight'))*scale+shift);k=np.load(P/'full_kv_attempt1'/(branch+'_k.npy'));v=np.load(P/'full_kv_attempt1'/(branch+'_v.npy')).reshape(S,16,128);k=rms(k.reshape(S,16,128),w('attn.norm_k.weight'));freq=fixture(branch,'rotary')[0].contiguous().view(torch.float32).numpy();k=apply_rope(k,freq)
 gold={n:fixture(branch,n)[0] for n in ['attention_output','ffn_input','ffn_output','post_ffn_norm','block_output']}
 for begin in range(0,S,64):
  end=min(begin+64,S);idx=np.arange(begin,end);M=len(idx);D=ROOT/(branch+'_'+str(begin));D.mkdir(exist_ok=True);record=D/'PASS.json'
  if record.exists():
   old=json.loads(record.read_text());assert old['begin']==begin and old['end']==end and all(digest(D/n)==h for n,h in old['files'].items());all_records.append(old);continue
  status(state='RUNNING',branch=branch,begin=begin,end=end,total_rows=S,passed_chunks=len(all_records));t=time.time();chunk_rows=[]
  q=linear(inp[idx],w('attn.to_q.weight')).reshape(M,16,128);q=rms(q,w('attn.norm_q.weight'));q=apply_rope(q,np.ascontiguousarray(freq[idx]));core=np.empty_like(q);assert flash.flash_cpu(q.ctypes.data,k.ctypes.data,v.ctypes.data,core.ctypes.data,M,S,ex.ctypes.data,None,6)==0
  out=linear(core.reshape(M,2048),w('attn.to_out.weight'),w('attn.to_out.bias'));checkstage(branch,'attention_output',out,gold['attention_output'][idx]);mid=rb(x[idx]+rb(gate*rms(out,w('norm_post_attn.weight'))));ffn=rb(rms(mid,w('norm2.weight'))*sc2+sh2);checkstage(branch,'ffn_input',ffn,gold['ffn_input'][idx]);ids,weights=free_router(ffn);slots=np.zeros((M*8,2048),dtype=np.float32);flat=ids.reshape(-1)
  for e in range(128):
   pos=np.where(flat==e)[0]
   if len(pos):slots[pos]=mlp(ffn[pos//8],state['ffn.experts.w1'][e].float().numpy(),state['ffn.experts.w3'][e].float().numpy(),state['ffn.experts.w2'][e].float().numpy())
  prod=slots.reshape(M,8,2048)*weights[:,:,None];streams=[(np.float32(0)+prod[:,i])+prod[:,i+4] for i in range(4)];routed=rb(((streams[0]+streams[1])+streams[2])+streams[3]);shared=mlp(ffn,w('ffn.shared_experts.gate_proj.weight'),w('ffn.shared_experts.up_proj.weight'),w('ffn.shared_experts.down_proj.weight'));fo=rb(routed+shared);checkstage(branch,'ffn_output',fo,gold['ffn_output'][idx]);post=rms(fo,w('norm_post_ffn.weight'));checkstage(branch,'post_ffn_norm',post,gold['post_ffn_norm'][idx]);bo=rb(mid+rb(ga2*post));checkstage(branch,'block_output',bo,gold['block_output'][idx]);np.save(D/'ids.npy',ids);np.save(D/'weights.npy',weights)
  rec=dict(branch=branch,begin=begin,end=end,rows=M,comparisons=chunk_rows,seconds=time.time()-t,files={q.name:digest(q) for q in D.glob('*.npy')});record.write_text(json.dumps(rec,indent=2));all_records.append(rec);print(json.dumps(dict(branch=branch,begin=begin,end=end,seconds=rec['seconds'],bit_mismatches=0)),flush=True)
  if time.time()-started>42000:status(state='STOPPED_BUDGET_CHECKPOINTS_PRESERVED',passed_chunks=len(all_records));raise SystemExit(77)
result=dict(status='PASS_LIMITED_LAYER0_STEP0_ALL_QUERY_ROWS',query_rows=sum(r['rows'] for r in all_records),chunks=len(all_records),comparisons=sum(len(r['comparisons']) for r in all_records),BF16_bit_mismatches=0,source_internal_Golden_injected=False,target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized(),host_GiB=128,HB_GiB=8,wall_seconds=time.time()-started,scope='same seen two CFG;all L0/step0 queries and full K/V, not48 layers/40steps or TI2V',independent_audit_pending=True)
(ROOT/'RESULT.json').write_text(json.dumps(result,indent=2));status(state='COMPLETE_NUMERICAL_RUN_AUDIT_PENDING',**{k:v for k,v in result.items() if k not in ['status','target_GPU_count','host_GiB','HB_GiB']});print(json.dumps(result),flush=True)
