import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
import pathlib,sys,json,hashlib,ctypes as C,time,traceback,numpy as np,torch
from safetensors import safe_open
R=pathlib.Path(__file__).resolve().parent;B=R.parent;P=B/'lingbot_step4_bitexact_20261029_v4';G=B/'lingbot_step3_capture_20261028_v1';F=P/'full_layer_stagewise_v1';rank=int(os.environ['SWE_RANK']);torch.set_num_threads(1);torch.set_num_interop_threads(1)
roundfile=R/('ROUND_N%02d'%rank);roundno=int(roundfile.read_text())+1 if roundfile.exists() else 1;roundfile.write_text(str(roundno));D=R/('case%d'%roundno)/('N%02d'%rank);D.mkdir(parents=True,exist_ok=False);os.umask(0o022)
sys.path.insert(0,str(P));from target_math_simd import tc,rb,rms
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
for n in ['um_store','um_load']:getattr(u,n).argtypes=[U,C.c_void_p,U]
for n in ['um_peer_send','um_peer_recv']:getattr(u,n).argtypes=[C.c_int,C.c_void_p,U]
u.um_compute.argtypes=[U,C.c_int,C.c_char_p]
def checkrc(rc):
 if rc:raise RuntimeError(u.um_error().decode())
def event(kind,label,start,**kw):log.append(dict(kind=kind,label=label,start=start,done=int(u.um_now()),rank=rank,**kw))
def hb(a,addr,label):
 a=np.ascontiguousarray(a);b=np.empty_like(a);t=int(u.um_now());checkrc(u.um_store(addr,a.ctypes.data,a.nbytes));checkrc(u.um_load(addr,b.ctypes.data,b.nbytes));ck('HB_'+label,np.array_equal(a.view(np.uint8),b.view(np.uint8)));event('HB',label,t,bytes=a.nbytes,addr=addr,sha256=digest(b));return b
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
 checkrc(u.um_init(str(D).encode()))
 for branch,S in [('cond',49883),('uncond',48986)]:
  idx=np.r_[0:32,S-32:S];local=np.flatnonzero(idx%16==rank);xx=fixture(branch,'block_input')[idx].float().numpy();temb=fixture(branch,'temb6_constant_row').float().numpy();mods=torch.from_numpy(temb+get('scale_shift_table')).chunk(6,-1);shift,scale,gatem,sh2,sc2,gatef=[z.numpy() for z in [mods[0],1+mods[1],mods[2].tanh(),mods[3],1+mods[4],mods[5].tanh()]];inp=rb(rms(xx,get('norm1.weight'))*scale+shift)
  qw=hbf(get('attn.to_q.weight',head=True),64*2**20,'Q_weight');q=rb(tc.matmul(inp,qw.T));q=rms(q,get('attn.norm_q.weight'));freq=fixture(branch,'rotary').contiguous().view(torch.float32).numpy();q=rope(q,np.ascontiguousarray(freq[idx]));k0=np.load(P/'full_kv_attempt1'/(branch+'_k.npy'),mmap_mode='r');v0=np.load(P/'full_kv_attempt1'/(branch+'_v.npy'),mmap_mode='r');k=np.ascontiguousarray(k0.reshape(S,16,128)[:,rank]);v=np.ascontiguousarray(v0.reshape(S,16,128)[:,rank]);k=rope(rms(k,get('attn.norm_k.weight')),np.ascontiguousarray(freq));k=hbf(k,0,'full_head_K');v=hbf(v,32*2**20,'full_head_V');q=hbf(q,128*2**20,'query_Q');core=np.empty_like(q);assert head.flash_head(q.ctypes.data,k.ctypes.data,v.ctypes.data,core.ctypes.data,64,S,ex.ctypes.data,None,6)==0;compute(4*64*S*128,'software_full_context_attention_head');np.save(D/(branch+'_core.npy'),core)
  carry=np.zeros((64,2048),dtype=np.float32) if rank==0 else recv(rank-1,(64,2048),np.float32,branch+'_Ocarry_'+str(rank-1));carry=hb(carry,160*2**20,'Ocarry_in');ow=get('attn.to_out.weight')[:,rank*128:(rank+1)*128].T.copy();ow=hbf(ow,64*2**20,'O_weight');t=int(u.um_now())
  for kpos in range(0,128,16):carry=tc.block_fma_batch(carry,np.ascontiguousarray(core[:,kpos:kpos+16]),np.ascontiguousarray(ow[kpos:kpos+16]))
  compute(2*64*2048*128,'software_original_order_O_head');carry=hb(carry,160*2**20,'Ocarry_out');np.save(D/(branch+'_carry.npy'),carry)
  if rank<15:send(rank+1,carry,branch+'_Ocarry_'+str(rank))
  else:
   attention=rb(carry+get('attn.to_out.bias'));np.save(D/(branch+'_attention.npy'),attention)
   for dest in range(15):send(dest,attention[np.flatnonzero(idx%16==dest)],branch+'_Oresult_'+str(dest))
  attention=attention[local] if rank==15 else recv(15,(len(local),2048),np.float32,branch+'_Oresult_'+str(rank));goldatt=fixture(branch,'attention_output')[idx[local]].float().numpy();ck(branch+'_attention_bits',np.array_equal(attention.view(np.uint32),goldatt.view(np.uint32)));mid=rb(xx[local]+rb(gatem*rms(attention,get('norm_post_attn.weight'))));fi=rb(rms(mid,get('norm2.weight'))*sc2+sh2);np.save(D/(branch+'_ffn_input.npy'),fi);ck(branch+'_ffn_input_bits',np.array_equal(fi.view(np.uint32),fixture(branch,'ffn_input')[idx[local]].float().numpy().view(np.uint32)))
  # Full batch counts are bound to previous autonomous full FFN pass, not captured GPU routes.
  binding=json.loads((F/branch/'ROUTE_BINDING.json').read_text());ck('full_count_autonomous',not binding['source_internal_Golden_injected']);ids=np.load(F/branch/'autonomous_ids.npy');weights=np.load(F/branch/'autonomous_weights.npy');counts=np.bincount(ids.reshape(-1),minlength=128);wrouter=hb(get('ffn.router.weight'),64*2**20,'router_FP32_weight');parts=np.empty((5,len(fi),128),dtype=np.float32);assert rr.split(fi.ctypes.data,wrouter.ctypes.data,parts.ctypes.data,len(fi),128,2048,5,8)==0;logits=parts[0]+parts[1]
  for z in parts[2:]:logits=logits+z
  scores=np.empty_like(logits);assert math.profile_sigmoid(logits.ctypes.data,scores.ctypes.data,scores.size)==0;ownids,ownweights,_=select(torch.from_numpy(scores),torch.from_numpy(get('ffn.router.e_score_correction_bias')));ck(branch+'_free_router',np.array_equal(ownids.numpy(),ids[idx[local]]) and np.array_equal(ownweights.float().numpy().view(np.uint32),weights[idx[local]].view(np.uint32)));slots=np.zeros((len(local),8,2048),dtype=np.uint16);seen=np.zeros((len(local),8),dtype=np.uint8);lookup={int(t):i for i,t in enumerate(idx[local])}
  shared=mlp(fi,['ffn.shared_experts.gate_proj.weight','ffn.shared_experts.up_proj.weight','ffn.shared_experts.down_proj.weight'],None,-1)
  selectedids=ids[idx]
  for e in range(128):
   owner=e%16
   for origin in range(16):
    tokenpos,slot=np.nonzero((selectedids==e)&((idx%16)[:,None]==origin))
    if not len(tokenpos):continue
    label=branch+'_e%d_o%d'%(e,origin);tokens=idx[tokenpos];M=len(tokens)
    if rank==origin:
     loc=np.array([lookup[int(t)] for t in tokens]);packet=np.empty((M,4112),dtype=np.uint8);meta=np.zeros((M,4),dtype=np.uint32);meta[:,0]=tokens;meta[:,1]=slot.astype(np.uint32)|(np.uint32(e)<<16);meta[:,2]=(weights[tokens,slot].view(np.uint32)>>16);meta[:,3]=np.uint32(origin)|(np.uint32(owner)<<16);packet[:,:16]=meta.view(np.uint8).reshape(M,16);packet[:,16:]=(fi[loc].view(np.uint32)>>16).astype(np.uint16).view(np.uint8).reshape(M,4096)
     if owner!=origin:send(owner,packet,label+'_dispatch')
    if rank==owner:
     if owner!=origin:packet=recv(origin,(M,4112),np.uint8,label+'_dispatch')
     packet=hb(packet,128*2**20,label+'_owner_input');pm=packet[:,:16].copy().view(np.uint32).reshape(M,4);ck('packet_identity',np.array_equal(pm[:,0],tokens) and np.all(pm[:,1]>>16==e) and np.array_equal(pm[:,1]&65535,slot));xin=(packet[:,16:].copy().view(np.uint16).astype(np.uint32)<<16).view(np.float32).reshape(M,2048);y=mlp(xin,['ffn.experts.w1','ffn.experts.w3','ffn.experts.w2'],e,int(counts[e]));packet[:,16:]=(y.view(np.uint32)>>16).astype(np.uint16).view(np.uint8).reshape(M,4096);packet=hb(packet,128*2**20,label+'_owner_output')
     if owner!=origin:send(origin,packet,label+'_return')
    if rank==origin:
     if owner!=origin:packet=recv(owner,(M,4112),np.uint8,label+'_return')
     ck('slot_once',np.all(seen[loc,slot]==0));slots[loc,slot]=packet[:,16:].copy().view(np.uint16).reshape(M,2048);seen[loc,slot]=1
  ck(branch+'_all_returns',np.all(seen==1));values=(slots.astype(np.uint32)<<16).view(np.float32);product=values*weights[idx[local],:,None];streams=[(np.float32(0)+product[:,i])+product[:,i+4] for i in range(4)];fo=rb(rb(((streams[0]+streams[1])+streams[2])+streams[3])+shared);post=rms(fo,get('norm_post_ffn.weight'));bo=rb(mid+rb(gatef*post))
  for name,a in [('ffn_output',fo),('post_ffn_norm',post),('block_output',bo)]:ck(branch+'_'+name+'_bits',np.array_equal(a.view(np.uint32),fixture(branch,name)[idx[local]].float().numpy().view(np.uint32)));np.save(D/(branch+'_'+name+'.npy'),a)
  (D/(branch+'_PASS.json')).write_text(json.dumps(dict(rank=rank,query_indices=idx[local].tolist(),source_internal_Golden_injected=False,full_batch_count_prerequisite='previous autonomous full step4 FFN/route binding',selected_experts_recomputed=True),indent=2))
 checkrc(u.um_shutdown());(D/'EVENTS.json').write_text(json.dumps(log,indent=2));(D/'CHECKS.json').write_text(json.dumps(checks,indent=2));(D/'PASS.json').write_text(json.dumps(dict(state='PASS_SELECTED_CONNECTED_TP_EP_CPU_PAYLOAD_NATIVE_GATE',rank=rank,round=roundno,checks=len(checks),target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized(),CPU_host_cost_included=False,full_SRAM_Bank_cost_included=False),indent=2))
except BaseException:
 (D/'EVENTS.json').write_text(json.dumps(log,indent=2));(D/'FAILURE.json').write_text(json.dumps(dict(error=traceback.format_exc()),indent=2));raise
