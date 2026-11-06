import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='4'
import pathlib,json,hashlib,time,traceback,struct,numpy as np,torch
R=pathlib.Path(__file__).resolve().parent;B=R.parent;P=B/'lingbot_step4_bitexact_20261029_v4';F=P/'full_layer_stagewise_v1';G=B/'lingbot_step3_capture_20261028_v1';start=time.time();torch.set_num_threads(4);os.umask(0o022);checks=[];records=[];messages=[];totals=[]
def sha(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(n,v):(R/n).write_text(json.dumps(v,indent=2))
def ck(n,b):
 checks.append(dict(name=n,passed=bool(b)));assert b,n
def accept_packet(mm,seen,S,expected_e,expected_origin,weightbits):
 tt=mm[:,0].astype(np.int64);ss=(mm[:,1]&65535).astype(np.int64);ee=mm[:,1]>>16
 if np.any(tt>=S) or np.any(ss>=8) or np.any(ee!=expected_e):raise ValueError('identity')
 if np.any(tt%16!=expected_origin) or np.any((mm[:,3]&65535)!=expected_origin) or np.any((mm[:,3]>>16)!=expected_e%16):raise ValueError('owner')
 if np.any(mm[:,2]!=weightbits[tt,ss]):raise ValueError('weight')
 idx=tt*8+ss
 if len(np.unique(idx))!=len(idx) or np.any(seen[idx]!=0):raise ValueError('duplicate')
 return idx
def bf(u):return (u.astype(np.uint32)<<16).view(np.float32)
def rb(x):
 u=x.view(np.uint32);return ((u+np.uint32(0x7fff)+((u>>16)&1))>>16).astype(np.uint16)
def validate_desc(d):
 q=P/d['file'];ck('input_sha_'+d['file'],sha(q)==d['sha256']);return q
try:
 audit=json.loads((F/'INDEPENDENT_AUDIT.json').read_text());ck('step4_gate',audit['status']=='PASS_LIMITED_FULL_SINGLE_LAYER_CPU_FUNCTIONAL' and audit['check_count']==30944 and not audit['failures'])
 for branch,S in [('cond',49883),('uncond',48986)]:
  D=F/branch;binding=json.loads((D/'ROUTE_BINDING.json').read_text());x=np.load(validate_desc(binding['ffn_input']),mmap_mode='r');ids=np.load(validate_desc(binding['ids']));weights=np.load(validate_desc(binding['weights']));wb=(weights.view(np.uint32)>>16).astype(np.uint16);ck(branch+'_autonomous',not binding['source_internal_Golden_injected']);out=np.lib.format.open_memmap(R/(branch+'_returned_slots.npy'),mode='w+',dtype=np.uint16,shape=(S*8,2048));seen=np.zeros(S*8,dtype=np.uint8);flat=ids.reshape(-1);branch_msgs=local=remote=0;selected=set(list(range(32))+list(range(S-32,S)));selected_rows=0;bytes_full=0
  for e in range(128):
   receipt=json.loads((D/('expert_'+str(e)+'_PASS.json')).read_text());expert=np.load(validate_desc(receipt['output']),mmap_mode='r');pos=np.flatnonzero(flat==e);ck('expert_positions_'+branch+'_'+str(e),len(pos)==receipt['M'] and hashlib.sha256(pos.tobytes()).hexdigest()==receipt['positions_sha256']);owner=e%16
   for origin in range(16):
    ix=np.flatnonzero((pos//8)%16==origin)
    if not len(ix):continue
    pp=pos[ix];tokens=pp//8;slots=pp%8;M=len(pp)
    # Real BF16 payload, identity and weight metadata are serialized and reloaded.
    meta=np.empty((M,4),dtype=np.uint32);meta[:,0]=tokens;meta[:,1]=slots.astype(np.uint32)|(np.uint32(e)<<16);meta[:,2]=wb[tokens,slots].astype(np.uint32);meta[:,3]=np.uint32(origin)|(np.uint32(owner)<<16)
    dispatch=np.empty((M,4112),dtype=np.uint8);dispatch[:,:16]=meta.view(np.uint8).reshape(M,16);dispatch[:,16:]=(x[tokens].view(np.uint32)>>16).astype(np.uint16).view(np.uint8).reshape(M,4096);wire=dispatch.tobytes();received=np.frombuffer(wire,dtype=np.uint8).reshape(M,4112).copy();ck('dispatch_'+branch+'_'+str(e)+'_'+str(origin),np.array_equal(received,dispatch));ret=np.empty_like(received);ret[:,:16]=received[:,:16];ret[:,16:]=np.ascontiguousarray(expert[ix]).view(np.uint8).reshape(M,4096);retwire=ret.tobytes();decoded=np.frombuffer(retwire,dtype=np.uint8).reshape(M,4112).copy();mm=decoded[:,:16].copy().view(np.uint32).reshape(M,4);tt=mm[:,0].astype(np.int64);ss=(mm[:,1]&65535).astype(np.int64);ee=mm[:,1]>>16;ck('return_identity',np.all(ee==e) and np.all(tt%16==origin) and np.array_equal(mm[:,2],wb[tt,ss]));idx=accept_packet(mm,seen,S,e,origin,wb);out[idx]=decoded[:,16:].copy().view(np.uint16).reshape(M,2048);seen[idx]=1
    row=dict(branch=branch,expert=e,origin=origin,owner=owner,assignments=M,dispatch_bytes=len(wire),return_bytes=len(retwire),dispatch_sha256=hashlib.sha256(wire).hexdigest(),return_sha256=hashlib.sha256(retwire).hexdigest(),local=origin==owner);messages.append(row);bytes_full+=len(wire)+len(retwire);branch_msgs+=1
    if origin==owner:local+=M
    else:remote+=M
    # A predeclared 64-query/branch subset gets unscaled real 4112B records in PopNet.
    for t,slot in zip(tokens,slots):
     if int(t) in selected and origin!=owner:
      for src,dst,kind in [(origin,owner,'dispatch'),(owner,origin,'return')]:
       seq=len(records)+1;records.append(dict(id=seq,branch=branch,token=int(t),slot=int(slot),expert=e,src=src,dst=dst,kind=kind,payload_bytes=4112,flits=(4112+31)//32))
  out.flush();ck(branch+'_all_slots_once',np.all(seen==1));shared=np.load(validate_desc(json.loads((D/'SHARED_PASS.json').read_text())['output']),mmap_mode='r');gold=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_ffn_output.pt'),weights_only=True)[0];mismatch=0
  for begin in range(0,S,128):
   end=min(begin+128,S);v=bf(np.asarray(out[begin*8:end*8])).reshape(end-begin,8,2048);prod=v*weights[begin:end,:,None];streams=[(np.float32(0)+prod[:,i])+prod[:,i+4] for i in range(4)];routed=bf(rb(((streams[0]+streams[1])+streams[2])+streams[3]));actual=rb(routed+bf(np.asarray(shared[begin:end])));ref=gold[begin:end].view(torch.uint16).numpy();bad=int(np.count_nonzero(actual!=ref));mismatch+=bad;ck('ffn_'+branch+'_'+str(begin),bad==0)
  totals.append(dict(branch=branch,rows=S,assignments=S*8,local_assignments=local,remote_assignments=remote,serialized_roundtrip_bytes=bytes_full,groups=branch_msgs,FFN_BF16_elements=S*2048,FFN_bit_mismatches=mismatch,slotfile_sha256=sha(R/(branch+'_returned_slots.npy'))));put('PROGRESS.json',dict(state='FUNCTIONAL_BRANCH_DONE',totals=totals))
 put('MESSAGES.json',messages);put('NOC_RECORDS.json',records)
 with (R/'bench.txt').open('w') as f:
  for r in records:
   tick=r['id']*500;f.write('%d %d %d %d %d 0\n'%(tick,tick,r['src'],r['dst'],r['flits']+1))
 # Explicitly reject duplicate, wrong-owner, BF16 corruption and premature-release examples.
 negative={}
 for label,mutate in [('duplicate',lambda q:q),('wrong_owner',lambda q:q.__setitem__((0,3),q[0,3]^np.uint32(1))),('weight_corruption',lambda q:q.__setitem__((0,2),q[0,2]^np.uint32(1)))]:
  q=mm.copy();mutate(q)
  try:accept_packet(q,seen if label=='duplicate' else np.zeros_like(seen),S,e,origin,wb);negative[label]=False
  except ValueError:negative[label]=True
 pending=seen.copy();pending[0]=0
 try:
  if not np.all(pending==1):raise ValueError('missing return')
  negative['premature_combine']=False
 except ValueError:negative['premature_combine']=True
 ck('negative_controls',all(negative.values()));put('FUNCTIONAL_RESULT.json',dict(status='PASS_LIMITED_EP16_FULL_ROUTE_SERIALIZATION_FFN_RESTORE',totals=totals,checks=checks,check_count=len(checks),negative_controls=negative,noc_records=len(records),GPU_count=0,precision='original mixed BF16/FP32',host_GiB=128,HB_GiB=8,source_expert_outputs='reuse step4 autonomous full-batch CPU outputs; no new expert arithmetic',transport='CPU serialization/reload; independent PopNet selected trace only, not coupled payload simulation',whole_step5=False,elapsed_seconds=time.time()-start));put('STATUS.json',dict(state='EP16_FUNCTIONAL_DONE_NOC_PENDING',whole_step5=False))
except BaseException:
 put('FAILURE.json',dict(traceback=traceback.format_exc()));raise
