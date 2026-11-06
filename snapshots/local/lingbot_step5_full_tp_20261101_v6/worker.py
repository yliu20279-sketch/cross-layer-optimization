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
 checkrc(u.um_init(str(D).encode()));ch=(U*3)();u.um_bank_challenges.argtypes=[C.POINTER(U)];checkrc(u.um_bank_challenges(ch));ck('bank_challenges',list(ch)==[2,1,3]);ck('SRAM_oob_rejected',u.um_sram_bad()==1)
 binding=json.loads((R/'JOIN_BINDING.json').read_text());EP=B/'lingbot_step5_full_ep_20261031_v5';tile_receipts=[]
 for branch,S in [('cond',49883),('uncond',48986)]:
  xx=fixture(branch,'block_input').float().numpy();temb=fixture(branch,'temb6_constant_row').float().numpy();mods=torch.from_numpy(temb+get('scale_shift_table')).chunk(6,-1);shift,scale,gatem,sh2,sc2,gatef=[z.numpy() for z in [mods[0],1+mods[1],mods[2].tanh(),mods[3],1+mods[4],mods[5].tanh()]];inp=rb(rms(xx,get('norm1.weight'))*scale+shift);freq=fixture(branch,'rotary').contiguous().view(torch.float32).numpy()
  qw=hbf(get('attn.to_q.weight',head=True),64*2**20,'Q_weight');ow=hbf(get('attn.to_out.weight')[:,rank*128:(rank+1)*128].T.copy(),66*2**20,'O_weight');bias=get('attn.to_out.bias');qnorm=get('attn.norm_q.weight');knorm=get('attn.norm_k.weight');normpost=get('norm_post_attn.weight');norm2=get('norm2.weight');normffn=get('norm_post_ffn.weight')
  k0=np.load(P/'full_kv_attempt1'/(branch+'_k.npy'),mmap_mode='r');v0=np.load(P/'full_kv_attempt1'/(branch+'_v.npy'),mmap_mode='r');k=rope(rms(np.ascontiguousarray(k0.reshape(S,16,128)[:,rank]),knorm),np.ascontiguousarray(freq));v=np.ascontiguousarray(v0.reshape(S,16,128)[:,rank]);k=hbf(k,0,'full_head_K');v=hbf(v,32*2**20,'full_head_V');N=len(range(rank,S,16));maps={n:np.lib.format.open_memmap(D/(branch+'_'+n+'.npy'),mode='w+',dtype=np.float32,shape=((S,128) if n=='core' else (N,2048))) for n in ['core','attention_output','ffn_input','mid','block_output']};seen=np.zeros(N,dtype=np.uint8);goldatt=fixture(branch,'attention_output');goldfi=fixture(branch,'ffn_input')
  for begin in range(0,S,64):
   end=min(begin+64,S);idx=np.arange(begin,end);M=len(idx);local=np.flatnonzero(idx%16==rank);loc=(idx[local]-rank)//16;folder=D/('tile_'+branch+'_'+str(begin));label=branch+'_t%d'%begin;t=time.monotonic();q=rb(tc.matmul(np.ascontiguousarray(inp[idx]),qw.T));compute(2*M*2048*128,'software_Q_projection');q=rope(rms(q,qnorm),np.ascontiguousarray(freq[idx]));q=hbf(q,128*2**20,'Q_query');core=np.empty_like(q);assert head.flash_head(q.ctypes.data,k.ctypes.data,v.ctypes.data,core.ctypes.data,M,S,ex.ctypes.data,None,6)==0;compute(4*M*S*128,'software_full_context_attention_head');maps['core'][idx]=core
   carry=np.zeros((M,2048),dtype=np.float32) if rank==0 else recv(rank-1,(M,2048),np.float32,label+'_carry_'+str(rank-1));carry=hb(carry,160*2**20,'Ocarry_in')
   for kp in range(0,128,16):carry=tc.block_fma_batch(carry,np.ascontiguousarray(core[:,kp:kp+16]),np.ascontiguousarray(ow[kp:kp+16]))
   compute(2*M*2048*128,'software_original_order_O_head');carry=hb(carry,160*2**20,'Ocarry_out')
   if rank<15:send(rank+1,carry,label+'_carry_'+str(rank))
   else:
    allatt=rb(carry+bias);bits=(allatt.view(np.uint32)>>16).astype(np.uint16)
    for dest in range(15):
     di=np.flatnonzero(idx%16==dest)
     if len(di):send(dest,bits[di],label+'_O_BF16_'+str(dest))
   if len(local):
    attention=allatt[local] if rank==15 else (recv(15,(len(local),2048),np.uint16,label+'_O_BF16_'+str(rank)).astype(np.uint32)<<16).view(np.float32);ref=goldatt[idx[local]].float().numpy();bad=int(np.count_nonzero(attention.view(np.uint32)!=ref.view(np.uint32)))
    if bad:
     folder.mkdir();np.save(folder/'core_actual.npy',core);np.save(folder/'partial_carry.npy',carry);np.save(folder/'attention_actual.npy',attention);np.save(folder/'attention_reference.npy',ref);raise RuntimeError('attention bit difference '+str(bad)+' '+label)
    mid=rb(xx[idx[local]]+rb(gatem*rms(attention,normpost)));fi=rb(rms(mid,norm2)*sc2+sh2);ref=goldfi[idx[local]].float().numpy();bad=int(np.count_nonzero(fi.view(np.uint32)!=ref.view(np.uint32)))
    if bad:
     folder.mkdir();np.save(folder/'core_actual.npy',core);np.save(folder/'partial_carry.npy',carry);np.save(folder/'ffn_actual.npy',fi);np.save(folder/'ffn_reference.npy',ref);raise RuntimeError('FFN input bit difference '+str(bad)+' '+label)
    ck('row_once',np.all(seen[loc]==0));seen[loc]=1;maps['attention_output'][loc]=attention;maps['ffn_input'][loc]=fi;maps['mid'][loc]=mid
   for a in maps.values():a.flush()
   receipt=dict(branch=branch,begin=begin,end=end,rank=rank,origin_rows=len(local),carry_sha256=digest(carry),core_sha256=digest(core),native_complete=int(u.um_now()),wall_seconds=time.monotonic()-t);tile_receipts.append(receipt)
   (D/'PROGRESS.json').write_text(json.dumps(dict(state='RUNNING_FULL_TP',branch=branch,verified_query_end=end,total=S,origin_rows_done=int(seen.sum()),native_complete=int(u.um_now())),indent=2))
  ck(branch+'_full_coverage',np.all(seen==1));key=branch+'_N%02d'%rank;bf=binding['files'][key];priorfi=EP/bf['input']['file'];priorfo=EP/bf['ffn']['file']
  for desc,q in [(bf['input'],priorfi),(bf['ffn'],priorfo)]:
   with q.open('rb') as f:ck('checkpoint_SHA',hashlib.file_digest(f,'sha256').hexdigest()==desc['sha256'])
  expected=np.load(priorfi,mmap_mode='r');ck(branch+'_full_join_input_bits',np.array_equal(maps['ffn_input'].view(np.uint32),expected.view(np.uint32)));fo=np.load(priorfo,mmap_mode='r');fo=hbf(fo,256*2**20,'verified_previous_native_MoE_FFN');post=rms(fo,normffn);bo=rb(maps['mid']+rb(gatef*post));goldbo=fixture(branch,'block_output')[np.arange(rank,S,16)].float().numpy();maps['block_output'][:]=bo;maps['block_output'].flush();ck(branch+'_composed_block_bits',np.array_equal(bo.view(np.uint32),goldbo.view(np.uint32)));(D/(branch+'_PASS.json')).write_text(json.dumps(dict(rank=rank,origin_rows=N,query_rows=S,source_internal_Golden_injected=False,MoE='verified prior native MoE checkpoint, exact full FFN input boundary',continuous_full_layer_timing=False),indent=2))
 checkrc(u.um_sram_finish());checkrc(u.um_shutdown());(D/'EVENTS.json').write_text(json.dumps(log,indent=2));(D/'TILES.json').write_text(json.dumps(tile_receipts,indent=2));(D/'CHECKS.json').write_text(json.dumps(checks,indent=2));(D/'PASS.json').write_text(json.dumps(dict(state='PASS_FULL_TP_CHECKPOINT_COMPOSITION',rank=rank,round=roundno,target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized(),whole_step5=False),indent=2))
except BaseException:
 (D/'EVENTS.json').write_text(json.dumps(log,indent=2));(D/'TILES.json').write_text(json.dumps(tile_receipts if 'tile_receipts' in globals() else [],indent=2));(D/'FAILURE.json').write_text(json.dumps(dict(error=traceback.format_exc()),indent=2));raise
