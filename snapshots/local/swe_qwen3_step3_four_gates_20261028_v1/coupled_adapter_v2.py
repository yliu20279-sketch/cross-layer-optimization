import ctypes as C,gzip,math,sys
from pathlib import Path
import numpy as np
import torch
from generated_adapter_v2 import GeneratedAdapter
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'swe_qwen3_token_commit_20261028_v1'));from native_runtime import Service,RT,base,FS_NS,ceildiv
class CompactLink:
 """Exact integer-fs descriptor serializer, packet runs retained analytically."""
 def __init__(self):self.free={'H2D':0,'D2H':0};self.credits=[[0]*16 for _ in range(4)];self.sequence=0;self.descriptors=[];self.packet_count=0
 def issue(self,direction,ready,payload,lease):
  assert 0<len(payload)<=65536;q=self.sequence%4;c=min(range(16),key=lambda i:float('inf') if self.credits[q][i] is None else self.credits[q][i]);a=self.credits[q][c]
  if a is None:raise RuntimeError('all credits pending')
  issue=max(ready,a);iommu=issue+20*FS_NS;start=max(iommu,self.free[direction]);full,tail=divmod(len(payload),256);step=ceildiv(256*100000000,5504);end=start+full*step+(ceildiv(tail*100000000,5504) if tail else 0);self.free[direction]=end;self.sequence+=1;self.credits[q][c]=None
  import hashlib
  d=dict(id=self.sequence,direction=direction,queue=q,credit=c,lease=lease,ready_fs=ready,issue_fs=issue,iommu_done_fs=iommu,start_fs=start,full_packets=full,tail_bytes=tail,packet_service_fs=step,serialize_done_fs=end,arrival_fs=end+250*FS_NS,bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),commit_fs=None)
  self.packet_count+=full+bool(tail);self.descriptors.append(d);return d
 def commit(self,d,now):
  if now<d['arrival_fs']:raise RuntimeError('endpoint before final packet')
  assert d['commit_fs'] is None and self.credits[d['queue']][d['credit']] is None;d['commit_fs']=now;self.credits[d['queue']][d['credit']]=now
class CoupledAdapter(GeneratedAdapter):
 def __init__(self,codec,library,out):
  super().__init__(codec,library);self.out=out;self.svc=Service(out);self.svc.link=CompactLink();self.p=RT(0,out);self.p.stage='continuous_two_layer_hybrid';self.svc.region(self.p,0,32*2**20,'immutable_weight_slot',['run_end']);self.next=64*2**20;self.nodes=[];self.reg={};self.tensor_nodes=[];self.context=[];self.host_ops=[];self.macros=[];self.versions=[];self.busy=False;self.weight_names={};self.phase=None;self.layer=None;self.handoffs=[];self.ends={};self.phase_checks=[];self.host_time=None
 def bind(self,states):
  import json,struct
  model=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');idx=json.loads((model/'model.safetensors.index.json').read_text())['weight_map'];heads={};self.weight_hosts={};offset=0
  for shard in sorted(set(idx.values())):
   with (model/shard).open('rb') as f:n=struct.unpack('<Q',f.read(8))[0];heads[shard]=json.loads(f.read(n))
  for key in sorted(idx):
   v=heads[idx[key]][key];offset=(offset+63)//64*64;self.weight_hosts[key]=offset;offset+=v['data_offsets'][1]-v['data_offsets'][0]
  assert offset==61064245248
  for layer,st in enumerate(states):
   for key,w in st.items():self.weight_names[w.data_ptr()]='model.layers.%d.'%layer+key
 def allocate(self,n,label):
  r=self.svc.region(self.p,self.next,n,label,['run_end']);self.next=(self.next+n+31)//32*32;return r
 def data(self,t):return t.detach().contiguous().view(torch.uint8).numpy().tobytes()
 def decode_bytes(self,data,t):return torch.from_numpy(np.frombuffer(data,dtype='u1').copy()).view(t.dtype).reshape(t.shape)
 def find(self,t):
  ptr=t.data_ptr();size=t.element_size()
  for rec in reversed(self.tensor_nodes):
   baseptr=rec['tensor'].data_ptr();n=rec['tensor'].numel()*size
   if t.dtype==rec['tensor'].dtype and baseptr<=ptr<baseptr+n:return rec,(ptr-baseptr)//size
  return None,0
 def publish(self,label,t,parents=None):
  if t.numel()==0:return t
  r=self.allocate(t.numel()*t.element_size(),label);self.svc.upload(self.p,r,self.data(t));node=dict(id=len(self.nodes),label=label,phase=self.phase,layer=self.layer,offset=r.offset,bytes=r.size,shape=list(t.shape),dtype=str(t.dtype),parents=list(parents if parents is not None else (self.context[-1] if self.context else [])),producer=r.producer,ready_ns=r.ready,execution='host_fallback_or_layout' if not label.startswith('native') else 'native_macro')
  data,event=self.svc.export(self.p,r,label+':expose');actual=self.decode_bytes(data,t);assert self.data(actual)==self.data(t),'publication mismatch';node['readers']=[dict(event=event,done_ns=self.p.now,consumer='host_expose')];self.nodes.append(node);rec=dict(tensor=actual,node=node,region=r);self.tensor_nodes.append(rec);self.reg[node['id']]=rec;return actual
 def ensure(self,t,label='host_layout_import'):
  rec,delta=self.find(t)
  if rec is not None:return rec,delta
  actual=self.publish(label,t);return self.find(actual)
 def host_input(self,t,label):
  if not isinstance(t,torch.Tensor):return t,None
  if t.numel()==0:return t,None
  if t.data_ptr() in self.weight_names:
   done=self.svc.dma.serve('host_CPU_parameter_read',self.p.now*FS_NS,t.numel()*t.element_size());self.p.sync(ceildiv(done,FS_NS),'host_parameter_ready');return t,'HOST:'+self.weight_names[t.data_ptr()]
  rec,delta=self.find(t)
  if rec is None:
   actual=self.publish('host_layout_contiguous_import',t);rec,_=self.find(actual);assert self.data(actual)==self.data(t);return actual,rec['node']['id']
  data,e=self.svc.export(self.p,rec['region'],label+':CPU_input');flat=torch.from_numpy(np.frombuffer(data,dtype='u1').copy()).view(t.dtype);actual=torch.as_strided(flat,t.shape,t.stride(),delta);assert self.data(actual)==self.data(t),'HB view mismatch';rec['node']['readers'].append(dict(event=e,done_ns=self.p.now,consumer=label));return actual,rec['node']['id']
 def host(self,name,args,func):
  xs=[];parents=[]
  for x in args:
   v,i=self.host_input(x,name);xs.append(v)
   if i is not None:parents.append(i)
  self.context.append(parents);start=self.p.now
  try:y=func(*xs)
  finally:self.context.pop()
  self.host_ops.append(dict(name=name,phase=self.phase,layer=self.layer,parents=parents,input_ready_ns=start,publication_end_ns=self.p.now,CPU_cost=None,scope='actual host source semantic fallback, not NPU arithmetic'))
  return y
 def note(self,name,tensor,**metadata):
  super().note(name,tensor,**metadata);return self.publish('host:'+name,tensor)
 def cast(self,x,dtype):return self.host('cast',[x],lambda x:super(CoupledAdapter,self).cast(x,dtype))
 def rmsnorm(self,x,scale,epsilon=1e-6):return self.host('rmsnorm',[x,scale],lambda x,s:super(CoupledAdapter,self).rmsnorm(x,s,epsilon))
 def add(self,a,b):return self.host('BF16_add',[a,b],lambda a,b:super(CoupledAdapter,self).add(a,b))
 def multiply(self,a,b):return self.host('BF16_multiply',[a,b],lambda a,b:super(CoupledAdapter,self).multiply(a,b))
 def softmax_fp32(self,x,dim=-1):return self.host('FP32_softmax',[x],lambda x:super(CoupledAdapter,self).softmax_fp32(x,dim))
 def topk(self,x,k):return self.host('CPU_source_topk',[x],lambda x:super(CoupledAdapter,self).topk(x,k))
 def gather(self,data,ids,axis=0):return self.host('gather',[data,ids],lambda a,b:super(CoupledAdapter,self).gather(a,b,axis))
 def index_add(self,data,ids,updates,axis=0):return self.host('index_add',[data,ids,updates],lambda a,b,c:super(CoupledAdapter,self).index_add(a,b,c,axis))
 def raw(self,x,w):
  if self.busy:raise RuntimeError('weight slot still has readers')
  x=x.contiguous().reshape(-1,x.shape[-1]);w=w.contiguous();M,K=x.shape;N=w.shape[0];assert w.shape[1]==K and w.numel()*2<=32*2**20
  rec,delta=self.ensure(x,'matrix_input_layout');assert delta==0 or x.is_contiguous();self.busy=True;vid=len(self.versions);weight_data=self.data(w);cache=next(r for r in self.p.regions if r.label=='immutable_weight_slot');key=self.weight_names.get(w.data_ptr(),'derived_attention_layout')
  if key in self.weight_hosts:hostaddr=self.weight_hosts[key]
  else:hostaddr=self.svc.io;self.svc.io+=(len(weight_data)+63)//64*64
  for off in range(0,len(weight_data),65536):
   chunk=weight_data[off:off+65536];lease=self.svc.pool.acquire(hostaddr+off,len(chunk),self.p.now*FS_NS);ready=self.svc.dma.serve('DMA_host_read',self.p.now*FS_NS,len(chunk));d=self.svc.link.issue('H2D',ready,chunk,lease);self.p.sync(ceildiv(d['arrival_fs'],FS_NS),'weight_H2D_arrive');self.p.event(1,'weight_slot_commit',byte_count=len(chunk),segments=[(off,len(chunk))]);self.svc.link.commit(d,self.p.now*FS_NS);self.svc.pool.hold(lease,self.p.now*FS_NS);self.svc.pool.release(lease,self.p.now*FS_NS);self.svc.transfers.append(dict(rank=0,label='weight_version%d'%vid,offset=off,event=self.p.last,descriptor=d['id'],bytes=len(chunk)))
  cache.ready=self.p.now;cache.producer=self.p.last;cache.shadow=torch.from_numpy(np.frombuffer(weight_data,dtype='u1').copy());version=dict(version=vid,key=key,host_address=hostaddr,bytes=len(weight_data),sha256=__import__('hashlib').sha256(weight_data).hexdigest(),producer=cache.producer,ready_ns=cache.ready,M=M,N=N,K=K,readers=[])
  self.svc.reject('active_weight_victim_%d'%vid,lambda:self.guard_reuse())
  # For views, stage the exact logical matrix as a charged host layout, not an invented activation.
  if delta or rec['tensor'].numel()!=x.numel() or rec['tensor'].shape!=x.shape:rec,_=self.ensure(self.publish('matrix_contiguous_layout',x))
  xb,xe,_=self.p.load(rec['region'],'matrix_input_BF16');self.p.need(xb);xb['remaining']=(N+63)//64
  outreg=self.allocate(M*N*4,'native_FP32_matrix_output');yt=base.Tensor(torch.empty((M,N),dtype=torch.float32),outreg.offset,'native_matrix')
  for n0 in range(0,N,64):
   nn=min(64,N-n0);wv=self.p.alloc((nn*K*2,),torch.uint8,'weight_BF16_tile');self.p.event(0,'weight_tile_read',byte_count=nn*K*2,segments=[(n0*K*2,nn*K*2)],deps=[cache.producer]);we=self.p.last;self.p.service(0,wv['bytes'],'weight_tile_fill');wv.update(data=cache.shadow[n0*K*2:(n0+nn)*K*2].clone(),ready=self.p.now,producer=self.p.last);wv['remaining']=1
   out=self.p.alloc((M,nn),torch.float32,'native_matrix_tile');scratch=self.p.alloc((max(72,M)*nn+128,),torch.float32,'source_accumulator_scratch')
   blocks=(K+((K if K<=384 else ((K+1)//2 if K<1536 else 768)))-1)//(K if K<=384 else ((K+1)//2 if K<1536 else 768))
   ops=2*M*nn*K+(143*nn if M==1 else M*nn*(2*blocks-1));read=8*M*nn*K+8*nn*(71 if M==1 else M*(blocks-1));write=8*M*nn*K+4*nn*(143 if M==1 else M*(2*blocks-1));self.p.service(read,write,'native_source_loop_SRAM')
   def calc():
    a=xb['data'].numpy();b=wv['data'].numpy();o=np.empty((M,nn),dtype='<f4');rc=self.lib.source_gemm(a.ctypes.data,b.ctypes.data,o.ctypes.data,M,nn,K);assert rc==0;return torch.from_numpy(o)
   self.p.compute(3,ops,'native_source_FP32_loop_macro',out,calc,[xb,wv]);xb['remaining']-=1;wv['remaining']=0;version['readers'].append(dict(event=self.p.last,weight_read_event=we,done_ns=self.p.now,n0=n0,nn=nn,ops=ops));self.svc.sram.append(dict(rank=0,buffers=[xb['id'],wv['id']],event=self.p.last,done_ns=self.p.now));self.p.free(wv,scratch);indices=(np.arange(M)[:,None]*N+np.arange(n0,n0+nn)[None,:]).reshape(-1);self.p.store(yt,out,indices,'native_matrix_tile_store');self.p.free(out)
  self.p.free(xb);rec['node']['readers'].append(dict(event=xe,done_ns=self.p.now,consumer='native_matrix'));outreg.shadow=yt.data.view(torch.uint8).reshape(-1).clone();outreg.ready=self.p.now;outreg.producer=yt.producer;self.svc.record(self.p,outreg,yt.data.numpy().tobytes());version['last_reader_ns']=self.p.now;self.versions.append(version);self.busy=False
  data,e=self.svc.export(self.p,outreg,'native_FP32_for_host_codec');self.svc.mark(self.p,outreg,'run_end',e);self.svc.retire(self.p,outreg);self.macros.append(dict(phase=self.phase,layer=self.layer,version=vid,M=M,N=N,K=K,input_node=rec['node']['id'],output_offset=outreg.offset,output_producer=yt.producer,complete_ns=self.p.now));return torch.from_numpy(np.frombuffer(data,dtype='<f4').copy()).reshape(*x.shape[:-1],N)
 def guard_reuse(self):
  if self.busy:raise RuntimeError('active immutable weight slot cannot be reused')
 def linear(self,x,w):
  original=x.shape;out=self.codec.round(self.raw(x,w)).reshape(*original[:-1],w.shape[0]);return self.note('generated_linear_BF16',out)
 def matmul(self,a,b):
  return self.host('attention_layout_inputs',[a,b],lambda a,b:super(CoupledAdapter,self).matmul(a,b))
 def begin_layer(self,phase,layer,x):
  self.phase=phase;self.layer=layer;rec,_=self.ensure(x,'external_layer0_input' if layer==0 else 'layer_handoff');self.p.sync(rec['region'].ready,'layer_input_ready')
  if layer==1:
   prior=self.ends[(phase,0)];assert prior['node']==rec['node']['id'];self.handoffs.append(dict(phase=phase,source_layer=0,dest_layer=1,node=rec['node']['id'],producer=rec['region'].producer,source_done_ns=prior['done_ns'],consumer_start_ns=self.p.now,offset=rec['region'].offset,restored=False))
 def end_layer(self,phase,layer,x):
  rec,_=self.find(x);assert rec;self.ends[(phase,layer)]=dict(node=rec['node']['id'],done_ns=self.p.now,offset=rec['region'].offset,producer=rec['region'].producer);self.phase_checks.append(dict(phase=phase,layer=layer,output_sha256=__import__('hashlib').sha256(self.data(x)).hexdigest(),node=rec['node']['id'],ready_ns=rec['region'].ready))
 def finish(self,cache):
  import json
  final_nodes={v['node'] for (phase,layer),v in self.ends.items() if layer==1};kv_nodes=set()
  for pair in cache.entries.values():
   for t in pair:
    rec,_=self.find(t)
    if rec:kv_nodes.add(rec['node']['id'])
  for node in self.nodes:
   rec=self.reg[node['id']];r=rec['region']
   last=max(node['readers'],key=lambda v:v['done_ns'])['event'];self.svc.mark(self.p,r,'run_end',last)
   if node['id'] in final_nodes or node['id'] in kv_nodes:
    self.svc.leases[(0,r.offset)]['pending']={'future_decode_KV'} if node['id'] in kv_nodes else {'downstream_layer2'}
   else:self.svc.retire(self.p,r)
  cache_region=next(r for r in self.p.regions if r.label=='immutable_weight_slot');self.svc.mark(self.p,cache_region,'run_end',self.versions[-1]['readers'][-1]['event']);self.svc.retire(self.p,cache_region)
  # publish() may allocate additional internal nodes only via the same registry.
  assert all(r.offset+r.size<=536870912 for r in self.p.regions);assert self.next<=536870912
  for name,v in [('NODES',self.nodes),('HOST_FALLBACK_OPS',self.host_ops),('NATIVE_MACROS',self.macros),('WEIGHT_SLOT_VERSIONS',self.versions),('LAYER_HANDOFFS',self.handoffs),('LAYER_OUTPUTS',self.phase_checks),('LINK_DESCRIPTOR_RUNS',self.svc.link.descriptors)]: (self.out/(name+'.json')).write_text(json.dumps(v,indent=2))
  self.svc.link.packets=[];self.svc.link.descriptors=[];self.svc.save();stats=self.p.finish();return dict(device=stats,tensor_nodes=len(self.nodes),matrix_calls=len(self.macros),weight_versions=len(self.versions),host_fallback_ops=len(self.host_ops),packet_count=self.svc.link.packet_count,HB_address_extent=self.next,retained_final_nodes=sorted(final_nodes),retained_KV_nodes=sorted(kv_nodes),CPU_cost=None,scope='N0 native memory and generic FP32 matrix macro checkpoints; RMSNorm/softmax/layout/other vector semantics explicit host fallback, not pure NPU or complete timing')
class CoupledKV:
 def __init__(self,bridge):self.bridge=bridge;self.entries={};self.events=[]
 def append(self,session,layer,key,value,positions):
  b=self.bridge;old=self.entries.get((session,layer));past=old[0].shape[-2] if old else 0
  if not torch.equal(positions,torch.arange(past,past+key.shape[-2],dtype=torch.int64)):raise ValueError('cache append positions not contiguous')
  if old:
   k,_=b.host_input(old[0],'cached_K_read');v,_=b.host_input(old[1],'cached_V_read');key=torch.cat((k,key),dim=-2);value=torch.cat((v,value),dim=-2)
  key=b.publish('KV_key_append',key);value=b.publish('KV_value_append',value);self.entries[(session,layer)]=(key,value);kr,_=b.find(key);vr,_=b.find(value);self.events.append(dict(phase=b.phase,layer=layer,past=past,length=key.shape[-2],key_node=kr['node']['id'],value_node=vr['node']['id'],ready_ns=b.p.now));return key,value
