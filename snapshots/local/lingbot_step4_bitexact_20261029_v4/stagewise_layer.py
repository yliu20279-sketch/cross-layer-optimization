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
D=P/'full_layer_stagewise_v1';D.mkdir(exist_ok=True);start=time.time();state={};refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references']
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
import hashlib
os.umask(0o022);os.nice(10);ROOT=D;job_started=time.time();A=[];B=[]
def sha(q):
 with pathlib.Path(q).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(q,r):
 tmp=pathlib.Path(str(q)+'.tmp');tmp.write_text(json.dumps(r,indent=2));tmp.replace(q)
def status(**kw):put(ROOT/'STATUS.json',dict(target_GPU_count=0,host_GiB=128,HB_GiB=8,OMP_threads=16,elapsed_seconds=time.time()-job_started,**kw))
def gate(branch,phase,begin,label,a,b,folder):
 b=b.float().numpy() if isinstance(b,torch.Tensor) else b
 bad=int((a.view(np.uint32)!=b.view(np.uint32)).sum());np.save(folder/(label+'.npy'),a)
 if bad:
  r=dict(state='STOPPED_NUMERICAL_DIFFERENCE',branch=branch,phase=phase,begin=begin,stage=label,bit_mismatches=bad,max_abs=float(np.abs(a-b).max()));put(folder/'FAILURE.json',r);status(**r);raise SystemExit(2)
 return dict(stage=label,elements=a.size,bit_mismatches=0)
def descriptor(q):return dict(file=str(q.relative_to(P)),sha256=sha(q))
def verify(d):
 q=P/d['file'];assert q.resolve().is_relative_to(P.resolve()) and sha(q)==d['sha256'];return q
def stageA(branch):
 x=fixture(branch,'block_input')[0].float().numpy();S=len(x);temb=fixture(branch,'temb6_constant_row').float();mod=(temb+state['scale_shift_table']).chunk(6,-1);shift,scale,gate_m,sh2,sc2,_=[a.numpy() for a in [mod[0],1+mod[1],mod[2].tanh(),mod[3],1+mod[4],mod[5].tanh()]]
 dest=ROOT/branch;dest.mkdir(exist_ok=True);full_path=dest/'autonomous_ffn_input.npy';ffnmap=np.lib.format.open_memmap(full_path,mode='r+' if full_path.exists() else 'w+',dtype=np.float32,shape=(S,2048));oldroot=P/'full_query_acceptance';inp=rb(rms(x,w('norm1.weight'))*scale+shift);k=np.load(P/'full_kv_attempt1'/(branch+'_k.npy'));v=np.load(P/'full_kv_attempt1'/(branch+'_v.npy')).reshape(S,16,128);k=rms(k.reshape(S,16,128),w('attn.norm_k.weight'));freq=fixture(branch,'rotary')[0].contiguous().view(torch.float32).numpy();k=apply_rope(k,freq);gold_attn=fixture(branch,'attention_output')[0];gold_ffn=fixture(branch,'ffn_input')[0]
 for begin in range(0,S,64):
  end=min(begin+64,S);idx=np.arange(begin,end);M=len(idx);folder=dest/('a_'+str(begin));folder.mkdir(exist_ok=True);receipt=folder/'PASS.json'
  if receipt.exists():
   r=json.loads(receipt.read_text());ffnmap[begin:end]=np.load(verify(r['ffn_input']));verify(r['attention_output']);A.append(r);continue
  status(state='RUNNING',phase='A_attention_and_FFN_input',branch=branch,begin=begin,end=end,total_rows=S,passed_A_chunks=len(A));t=time.time();legacy=oldroot/(branch+'_'+str(begin));old=legacy/'PASS.json'
  if old.exists():
   old=json.loads(old.read_text());assert old['begin']==begin and old['end']==end and all(sha(legacy/n)==h for n,h in old['files'].items());attn_path=legacy/'attention_output.npy';ffn_path=legacy/'ffn_input.npy';out=np.load(attn_path);fi=np.load(ffn_path)
   assert np.array_equal(out.view(np.uint32),gold_attn[idx].float().numpy().view(np.uint32)) and np.array_equal(fi.view(np.uint32),gold_ffn[idx].float().numpy().view(np.uint32));reused=True
  else:
   q=linear(inp[idx],w('attn.to_q.weight')).reshape(M,16,128);q=rms(q,w('attn.norm_q.weight'));q=apply_rope(q,np.ascontiguousarray(freq[idx]));core=np.empty_like(q);assert flash.flash_cpu(q.ctypes.data,k.ctypes.data,v.ctypes.data,core.ctypes.data,M,S,ex.ctypes.data,None,6)==0;out=linear(core.reshape(M,2048),w('attn.to_out.weight'),w('attn.to_out.bias'));gate(branch,'A',begin,'attention_output',out,gold_attn[idx],folder);mid=rb(x[idx]+rb(gate_m*rms(out,w('norm_post_attn.weight'))));fi=rb(rms(mid,w('norm2.weight'))*sc2+sh2);gate(branch,'A',begin,'ffn_input',fi,gold_ffn[idx],folder);attn_path=folder/'attention_output.npy';ffn_path=folder/'ffn_input.npy';reused=False
  ffnmap[begin:end]=fi;ffnmap.flush();r=dict(branch=branch,begin=begin,end=end,attention_output=descriptor(attn_path),ffn_input=descriptor(ffn_path),reused_legacy_A_only=reused,seconds=time.time()-t,bit_mismatches=0);put(receipt,r);A.append(r)
  if not reused:print(json.dumps(dict(phase='A',branch=branch,begin=begin,end=end,seconds=r['seconds'],bit_mismatches=0)),flush=True)
 ffnmap.flush();put(dest/'A_COMPLETE.json',dict(rows=S,ffn_input=descriptor(full_path),source_internal_Golden_injected=False));return S

def batch_mlp(x,w1,w3,w2):
 ga=expert_linear(x,w1);up=expert_linear(x,w3);act=np.empty_like(ga);assert math.profile_silu(ga.ctypes.data,act.ctypes.data,ga.size)==0;return expert_linear(rb(rb(act)*up),w2)
def stageB(branch,S):
 dest=ROOT/branch;ffn_desc=json.loads((dest/'A_COMPLETE.json').read_text())['ffn_input'];full=np.load(verify(ffn_desc),mmap_mode='r');ids,weights=free_router(full);assert (ids>=0).all() and (ids<128).all() and (np.diff(np.sort(ids,axis=1),axis=1)>0).all();flat=ids.reshape(-1);counts=np.bincount(flat,minlength=128);np.save(dest/'autonomous_ids.npy',ids);np.save(dest/'autonomous_weights.npy',weights);put(dest/'ROUTE_BINDING.json',dict(source_internal_Golden_injected=False,ffn_input=ffn_desc,ids=descriptor(dest/'autonomous_ids.npy'),weights=descriptor(dest/'autonomous_weights.npy'),counts=counts.tolist()));slotpath=dest/'expert_slots_bf16.npy';slots=np.lib.format.open_memmap(slotpath,mode='r+' if slotpath.exists() else 'w+',dtype=np.uint16,shape=(S*8,2048))
 for e in range(128):
  pos=np.where(flat==e)[0]
  if not len(pos):continue
  receipt=dest/('expert_'+str(e)+'_PASS.json');outpath=dest/('expert_'+str(e)+'.npy')
  if receipt.exists():r=json.loads(receipt.read_text());assert r['M']==len(pos) and r['positions_sha256']==hashlib.sha256(pos.tobytes()).hexdigest();output=np.load(verify(r['output']))
  else:
   status(state='RUNNING',phase='B_experts_actual_autonomous_batch',branch=branch,expert=e,M=len(pos));out=batch_mlp(np.ascontiguousarray(full[pos//8]),state['ffn.experts.w1'][e].float().numpy(),state['ffn.experts.w3'][e].float().numpy(),state['ffn.experts.w2'][e].float().numpy());output=(out.view(np.uint32)>>16).astype(np.uint16);np.save(outpath,output);r=dict(expert=e,M=len(pos),positions_sha256=hashlib.sha256(pos.tobytes()).hexdigest(),output=descriptor(outpath));put(receipt,r);print(json.dumps(dict(phase='B_expert',branch=branch,expert=e,M=len(pos))),flush=True)
  slots[pos]=output;slots.flush()
 shared_path=dest/'shared_bf16.npy';shared_receipt=dest/'SHARED_PASS.json'
 if shared_receipt.exists():shared=np.load(verify(json.loads(shared_receipt.read_text())['output']),mmap_mode='r')
 else:
  status(state='RUNNING',phase='B_shared_actual_full_batch',branch=branch,M=S);shared_float=mlp(full,w('ffn.shared_experts.gate_proj.weight'),w('ffn.shared_experts.up_proj.weight'),w('ffn.shared_experts.down_proj.weight'));np.save(shared_path,(shared_float.view(np.uint32)>>16).astype(np.uint16));put(shared_receipt,dict(output=descriptor(shared_path)));shared=np.load(shared_path,mmap_mode='r')
 x=fixture(branch,'block_input')[0].float().numpy();temb=fixture(branch,'temb6_constant_row').float();mods=(temb+state['scale_shift_table']).chunk(6,-1);gate_m=mods[2].tanh().numpy();gate_f=mods[5].tanh().numpy();gold={n:fixture(branch,n)[0] for n in ['ffn_output','post_ffn_norm','block_output']}
 for begin in range(0,S,64):
  end=min(begin+64,S);M=end-begin;folder=dest/('b_'+str(begin));folder.mkdir(exist_ok=True);receipt=folder/'PASS.json'
  if receipt.exists():r=json.loads(receipt.read_text());[verify(d) for d in r['files'].values()];B.append(r);continue
  status(state='RUNNING',phase='B_restore_postnorm_block_commit',branch=branch,begin=begin,end=end);part=(np.asarray(slots[begin*8:end*8]).astype(np.uint32)<<16).view(np.float32).reshape(M,8,2048);prod=part*weights[begin:end,:,None];streams=[(np.float32(0)+prod[:,i])+prod[:,i+4] for i in range(4)];routed=rb(((streams[0]+streams[1])+streams[2])+streams[3]);sf=(np.asarray(shared[begin:end]).astype(np.uint32)<<16).view(np.float32);fo=rb(routed+sf);checks=[gate(branch,'B',begin,'ffn_output',fo,gold['ffn_output'][begin:end],folder)];post=rms(fo,w('norm_post_ffn.weight'));checks.append(gate(branch,'B',begin,'post_ffn_norm',post,gold['post_ffn_norm'][begin:end],folder));ar=json.loads((dest/('a_'+str(begin))/'PASS.json').read_text());attn=np.load(verify(ar['attention_output']));mid=rb(x[begin:end]+rb(gate_m*rms(attn,w('norm_post_attn.weight'))));bo=rb(mid+rb(gate_f*post));checks.append(gate(branch,'B',begin,'block_output',bo,gold['block_output'][begin:end],folder));r=dict(branch=branch,begin=begin,end=end,checks=checks,files={n:descriptor(folder/(n+'.npy')) for n in ['ffn_output','post_ffn_norm','block_output']});put(receipt,r);B.append(r)
try:
 assert json.loads((P/'FFN_REPAIR_V2_RESULT.json').read_text())['new_bit_mismatches']==0
 sizes={branch:stageA(branch) for branch in ['cond','uncond']}
 for branch,S in sizes.items():stageB(branch,S)
 result=dict(status='PASS_LIMITED_FULL_SINGLE_LAYER_NUMERICAL_AUDIT_PENDING',query_rows=sum(sizes.values()),A_chunks=len(A),B_chunks=len(B),source_internal_Golden_injected=False,route_counts_derived_from_autonomous_full_FFN_inputs=True,target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized(),host_GiB=128,HB_GiB=8,precision='original mixed BF16/FP32',elapsed_seconds=time.time()-job_started,scope='same seen layer0/step0 dualCFG; not48layer/40step/TI2V or target timing');put(ROOT/'RESULT.json',result);status(state='COMPLETE_NUMERICAL_AUDIT_PENDING',**{k:v for k,v in result.items() if k not in ['status','target_GPU_count','host_GiB','HB_GiB','elapsed_seconds']})
except SystemExit:raise
except BaseException as e:status(state='STOPPED_PROCESS_EXCEPTION',exception=repr(e));raise
