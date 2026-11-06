import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
import pathlib,sys,json,hashlib,ctypes as C,time,traceback,numpy as np,torch
from safetensors import safe_open
R=pathlib.Path(__file__).resolve().parent;B=R.parent;P=B/'lingbot_step4_bitexact_20261029_v4';G=B/'lingbot_step3_capture_20261028_v1';F=P/'full_layer_stagewise_v1';rank=int(os.environ['SWE_RANK']);torch.set_num_threads(1);torch.set_num_interop_threads(1)
roundfile=R/('ROUND_N%02d'%rank);roundno=int(roundfile.read_text())+1 if roundfile.exists() else 1;roundfile.write_text(str(roundno));D=R/('case%d'%roundno)/('N%02d'%rank);D.mkdir(parents=True,exist_ok=False);os.umask(0o022)
sys.path.insert(0,str(P));from math_local import tc,rb,rms
refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'];cache={};log=[];checks=[]
def get(n,expert=None,head=False):
 ref=next(r for r in refs if r['name']=='blocks.0.'+n)
 with safe_open(ref['canonical_file'],framework='pt',device='cpu') as sf:
  if expert is not None:t=sf.get_slice(ref['name'])[expert]
  elif head:t=sf.get_slice(ref['name'])[rank*128:(rank+1)*128]
  else:t=sf.get_tensor(ref['name'])
 return t.float().numpy()
def fixture(branch,n):return torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_'+n+'.pt'),weights_only=True)[0]
def ck(n,b):checks.append(dict(name=n,passed=bool(b)));assert b,n
def digest(a):return hashlib.sha256(a.tobytes()).hexdigest()
u=C.CDLL(str(R/'libpeer.so'));U=C.c_uint64
u.um_init.argtypes=[C.c_char_p];u.um_error.restype=C.c_char_p;u.um_now.restype=U
for n in ['um_store','um_load','um_sram_load']:getattr(u,n).argtypes=[U,C.c_void_p,U]
for n in ['um_peer_send','um_peer_recv']:getattr(u,n).argtypes=[C.c_int,C.c_void_p,U]
u.um_compute.argtypes=[U,C.c_int,C.c_char_p]
def checkrc(rc):
 if rc:raise RuntimeError(u.um_error().decode())
def event(kind,label,start,**kw):log.append(dict(kind=kind,label=label,start=start,done=int(u.um_now()),rank=rank,**kw))
def hb(a,addr,label):
 a=np.ascontiguousarray(a);b=np.empty_like(a);t=int(u.um_now());checkrc(u.um_store(addr,a.ctypes.data,a.nbytes));checkrc(u.um_sram_load(addr,b.ctypes.data,b.nbytes));ck('HB_'+label,np.array_equal(a.view(np.uint8),b.view(np.uint8)));event('HB',label,t,bytes=a.nbytes,addr=addr,sha256=digest(b));return b
def hbf(a,addr,label):return (hb((a.view(np.uint32)>>16).astype(np.uint16),addr,label).astype(np.uint32)<<16).view(np.float32)
def send(dst,a,label):
 a=np.ascontiguousarray(a);t=int(u.um_now());checkrc(u.um_peer_send(dst,a.ctypes.data,a.nbytes));event('send',label,t,peer=dst,bytes=a.nbytes,sha256=digest(a))
def recv(src,shape,dtype,label):
 a=np.empty(shape,dtype=dtype);t=int(u.um_now());checkrc(u.um_peer_recv(src,a.ctypes.data,a.nbytes));event('recv',label,t,peer=src,bytes=a.nbytes,sha256=digest(a));return a
math=C.CDLL(str(P/'libprofile_math.so'));math.profile_math_open.argtypes=[C.c_char_p];assert math.profile_math_open(str(P/'sfu_profile').encode())==0
for n in ['profile_silu','profile_sigmoid']:getattr(math,n).argtypes=[C.c_void_p]*2+[C.c_size_t]
rr=C.CDLL(str(P/'librouter_split_strided.so'));rr.split.argtypes=[C.c_void_p]*3+[C.c_int]*5
head=C.CDLL(str(R/'libflash_head.so'));head.flash_head.argtypes=[C.c_void_p]*4+[C.c_int]*2+[C.c_void_p]*2+[C.c_int];head.rope_head.argtypes=[C.c_void_p]*3+[C.c_int]*2;ex=np.memmap(P/'sfu_profile/ex2_all_f32.raw',dtype=np.uint32,mode='r');sys.path.insert(0,str(B/'lingbot_step4_router_repair_20261028_v2'));from router_contract import select
recipes={(x['M'],x['N'],x['K']):x['recipe'] for x in json.loads((P/'GEMM_BATCH_RECIPES.json').read_text())['recipes']}
def compute(ops,label):
 t=int(u.um_now());checkrc(u.um_compute(ops,0,label.encode()));event('compute_proxy',label,t,ops=ops)
def elinear(x,w,globalM):
 rec='single_FDA16' if globalM==-1 else recipes[(globalM,len(w),x.shape[1])]
 if rec=='single_FDA16':y=tc.matmul(np.ascontiguousarray(x),np.ascontiguousarray(w.T))
 else:
  ps=[tc.matmul(np.ascontiguousarray(x[:,i*384:min((i+1)*384,x.shape[1])]),np.ascontiguousarray(w[:,i*384:min((i+1)*384,x.shape[1])].T)) for i in range(6)];y=ps[0]+ps[1]
  for z in ps[2:]:y=y+z
 compute(2*len(x)*w.size,'software_FDA_GEMM');return rb(y)
def mlp(x,names,e,globalM):
 weights=[hbf(get(n,e),64*2**20,'weight_'+n+'_'+str(e)) for n in names];gate=elinear(x,weights[0],globalM);up=elinear(x,weights[1],globalM);act=np.empty_like(gate);assert math.profile_silu(gate.ctypes.data,act.ctypes.data,gate.size)==0;return elinear(rb(rb(act)*up),weights[2],globalM)
def rope(x,f):
 y=np.empty_like(x);assert head.rope_head(x.ctypes.data,f.ctypes.data,y.ctypes.data,len(x),2)==0;return rb(y)
try:
 checkrc(u.um_init(str(D).encode()));ch=(U*3)();u.um_bank_challenges.argtypes=[C.POINTER(U)];checkrc(u.um_bank_challenges(ch));ck('actual_bank_challenges',list(ch)==[2,1,3]);ck('SRAM_oob_rejected',u.um_sram_bad()==1)
 for branch,S in [('cond',49883),('uncond',48986)]:
  idx=np.arange(S,dtype=np.int64);local=np.flatnonzero(idx%16==rank);binding=json.loads((F/branch/'ROUTE_BINDING.json').read_text());source=P/binding['ffn_input']['file'];ck('full_FFN_input_SHA',hashlib.sha256(source.read_bytes()).hexdigest()==binding['ffn_input']['sha256']);fi=np.load(source,mmap_mode='r')[local].copy();fi=hbf(fi,0,'full_origin_FFN_input');np.save(D/(branch+'_ffn_input.npy'),fi)
  # Full batch counts are bound to previous autonomous full FFN pass, not captured GPU routes.
  binding=json.loads((F/branch/'ROUTE_BINDING.json').read_text());ck('full_count_autonomous',not binding['source_internal_Golden_injected']);ids=np.load(F/branch/'autonomous_ids.npy');weights=np.load(F/branch/'autonomous_weights.npy');counts=np.bincount(ids.reshape(-1),minlength=128);wrouter=hb(get('ffn.router.weight'),64*2**20,'router_FP32_weight');parts=np.empty((5,len(fi),128),dtype=np.float32);assert rr.split(fi.ctypes.data,wrouter.ctypes.data,parts.ctypes.data,len(fi),128,2048,5,8)==0;logits=parts[0]+parts[1]
  for z in parts[2:]:logits=logits+z
  scores=np.empty_like(logits);assert math.profile_sigmoid(logits.ctypes.data,scores.ctypes.data,scores.size)==0;ownids,ownweights,_=select(torch.from_numpy(scores),torch.from_numpy(get('ffn.router.e_score_correction_bias')));ck(branch+'_free_router',np.array_equal(ownids.numpy(),ids[idx[local]]) and np.array_equal(ownweights.float().numpy().view(np.uint32),weights[idx[local]].view(np.uint32)));slots=np.zeros((len(local),8,2048),dtype=np.uint16);seen=np.zeros((len(local),8),dtype=np.uint8);lookup={int(t):i for i,t in enumerate(idx[local])}
  shared=mlp(fi,['ffn.shared_experts.gate_proj.weight','ffn.shared_experts.up_proj.weight','ffn.shared_experts.down_proj.weight'],None,-1)
  selectedids=ids[idx]
  for e in range(128):
   owner=e%16;groups=[];received_packets=[];all_tokenpos,all_slot=np.nonzero(selectedids==e)
   for origin in range(16):
    mask=idx[all_tokenpos]%16==origin;tokenpos=all_tokenpos[mask];slot=all_slot[mask]
    if not len(tokenpos):continue
    tokens=idx[tokenpos];M=len(tokens);label=branch+'_e%d_o%d'%(e,origin);groups.append((origin,tokens,slot,label))
    if rank==origin:
     loc=np.array([lookup[int(t)] for t in tokens]);packet=np.empty((M,4112),dtype=np.uint8);meta=np.zeros((M,4),dtype=np.uint32);meta[:,0]=tokens;meta[:,1]=slot.astype(np.uint32)|(np.uint32(e)<<16);meta[:,2]=(weights[tokens,slot].view(np.uint32)>>16);meta[:,3]=np.uint32(origin)|(np.uint32(owner)<<16);packet[:,:16]=meta.view(np.uint8).reshape(M,16);packet[:,16:]=(fi[loc].view(np.uint32)>>16).astype(np.uint16).view(np.uint8).reshape(M,4096)
     if owner!=origin:send(owner,packet,label+'_dispatch')
    if rank==owner:
     if owner!=origin:packet=recv(origin,(M,4112),np.uint8,label+'_dispatch')
     packet=hb(packet,128*2**20,label+'_owner_input');pm=packet[:,:16].copy().view(np.uint32).reshape(M,4);ck('packet_identity',np.array_equal(pm[:,0],tokens) and np.all(pm[:,1]>>16==e) and np.array_equal(pm[:,1]&65535,slot) and np.array_equal(pm[:,2],weights[tokens,slot].view(np.uint32)>>16) and np.all(pm[:,3]==(np.uint32(origin)|(np.uint32(owner)<<16))));received_packets.append(packet)
   if rank==owner and received_packets:
    joined=np.concatenate(received_packets);xin=(joined[:,16:].copy().view(np.uint16).astype(np.uint32)<<16).view(np.float32).reshape(len(joined),2048);y=mlp(xin,['ffn.experts.w1','ffn.experts.w3','ffn.experts.w2'],e,int(counts[e]));joined[:,16:]=(y.view(np.uint32)>>16).astype(np.uint16).view(np.uint8).reshape(len(joined),4096);joined=hb(joined,128*2**20,branch+'_expert%d_batched_output'%e);offset=0
   for origin,tokens,slot,label in groups:
    M=len(tokens)
    if rank==owner:
     packet=joined[offset:offset+M].copy();offset+=M
     if owner!=origin:send(origin,packet,label+'_return')
    if rank==origin:
     if owner!=origin:packet=recv(owner,(M,4112),np.uint8,label+'_return')
     loc=np.array([lookup[int(t)] for t in tokens]);ck('slot_once',np.all(seen[loc,slot]==0));slots[loc,slot]=packet[:,16:].copy().view(np.uint16).reshape(M,2048);seen[loc,slot]=1
  ck(branch+'_all_returns',np.all(seen==1));slots=hb(slots,256*2**20,branch+'_full_return_slots');values=(slots.astype(np.uint32)<<16).view(np.float32);product=values*weights[idx[local],:,None];streams=[(np.float32(0)+product[:,i])+product[:,i+4] for i in range(4)];fo=rb(rb(((streams[0]+streams[1])+streams[2])+streams[3])+shared);post=rms(fo,get('norm_post_ffn.weight'))
  for name,a in [('ffn_output',fo),('post_ffn_norm',post)]:ck(branch+'_'+name+'_bits',np.array_equal(a.view(np.uint32),fixture(branch,name)[idx[local]].float().numpy().view(np.uint32)));np.save(D/(branch+'_'+name+'.npy'),a)
  (D/(branch+'_PASS.json')).write_text(json.dumps(dict(rank=rank,query_indices=idx[local].tolist(),source_internal_Golden_injected=False,full_batch_count_prerequisite='previous autonomous full step4 FFN/route binding',selected_experts_recomputed=True),indent=2))
 checkrc(u.um_sram_finish());checkrc(u.um_shutdown());(D/'EVENTS.json').write_text(json.dumps(log,indent=2));(D/'CHECKS.json').write_text(json.dumps(checks,indent=2));(D/'PASS.json').write_text(json.dumps(dict(state='PASS_FULL_EP_CPU_PAYLOAD_NATIVE_GATE',rank=rank,round=roundno,checks=len(checks),target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized(),CPU_host_cost_included=False,full_SRAM_Bank_cost_included=False),indent=2))
except BaseException:
 (D/'EVENTS.json').write_text(json.dumps(log,indent=2));(D/'FAILURE.json').write_text(json.dumps(dict(error=traceback.format_exc()),indent=2));raise
