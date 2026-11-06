import sys
from common import *
sys.path.insert(0,str(B/'swe_qwen3_activation_noc_20261027_v1'));from runtime import Peer,NoC,base,certificate
sys.path.insert(0,str(B/'swe_qwen3_bf16_functional_v1_20261026'));from bf16_adapter import NativeCodec
sys.path.insert(0,str(B/'swe_qwen3_host_boundary_20261027_v1'));from boundary_service_v2 import Link,LeasePool,HostDMAService,FS_NS,ceildiv
class RT(Peer):
 def free(self,*bs):
  for b in bs:
   if b.get('remaining',0):raise RuntimeError('SRAM final arithmetic reader pending')
  return super().free(*bs)
 def op(self,shape,label,fn,reads):
  self.need(*reads);out=self.alloc(shape,torch.float32,label);self.service(sum(b['bytes'] for b in reads),out['bytes'],label+':SRAM');self.compute(3,out['bytes']//4,label,out,fn,reads);return out
class Service:
 def __init__(self,d):
  self.d=d;self.codec=NativeCodec(B/'swe_qwen3_bf16_functional_v1_20261026/libbf16_codec_bridge.so');self.link=Link();self.pool=LeasePool();self.dma=HostDMAService();self.transfers=[];self.res=[];self.leases={};self.readers=[];self.sram=[];self.negative=[];self.io=64*2**30
 def reject(self,name,fn):
  try:fn()
  except RuntimeError:self.negative.append(name)
  else:raise AssertionError(name)
 def region(self,p,offset,size,label,readers):
  r=p.region(offset,size,label);self.leases[(p.rank,offset)]=dict(region=r,label=label,pending=set(readers),retired=None)
  self.reject('%d:%s:unresident'%(p.rank,label),lambda:p.load(r,'negative_unresident'));return r
 def mark(self,p,r,name,event):
  v=self.leases[(p.rank,r.offset)]
  if name not in v['pending']:raise RuntimeError('missing/duplicate reader registration')
  v['pending'].remove(name);self.readers.append(dict(rank=p.rank,label=r.label,offset=r.offset,reader=name,event=event,done_ns=p.now))
 def retire(self,p,r):
  v=self.leases[(p.rank,r.offset)]
  if v['pending'] or v['retired'] is not None:raise RuntimeError('premature or duplicate HB retirement')
  v['retired']=p.now;r.retired=True
 def record(self,p,r,data):
  self.res.append(dict(rank=p.rank,label=r.label,offset=r.offset,global_address=r.global_address,bytes=r.size,ready_ns=r.ready,event=r.producer,sha256=sha(data)))
 def upload(self,p,r,data,host=None):
  if host is None:host=self.io;self.io+=(len(data)+63)//64*64
  assert host+len(data)<128*2**30
  buf=bytearray(len(data))
  for off in range(0,len(data),65536):
   chunk=data[off:off+65536];lease=self.pool.acquire(host+off,len(chunk),p.now*FS_NS);ready=self.dma.serve('DMA_host_read',p.now*FS_NS,len(chunk));d=self.link.issue('H2D',ready,chunk,lease);p.sync(ceildiv(d['arrival_fs'],FS_NS),r.label+':H2D_arrive')
   p.event(1,r.label+':H2D_commit',byte_count=len(chunk),segments=[(r.offset+off,len(chunk))]);buf[off:off+len(chunk)]=chunk;self.link.commit(d,p.now*FS_NS);self.pool.hold(lease,p.now*FS_NS);self.pool.release(lease,p.now*FS_NS)
   self.transfers.append(dict(rank=p.rank,label=r.label,offset=off,event=p.last,descriptor=d['id'],bytes=len(chunk)))
  r.shadow=torch.from_numpy(np.frombuffer(buf,dtype='u1').copy());r.ready=p.now;r.producer=p.last;self.record(p,r,data)
 def export(self,p,r,label):
  v,e,_=p.load(r,label+':HB_read');p.need(v);p.service(v['bytes'],0,label+':drain');data=v['data'].numpy().tobytes();p.free(v)
  for off in range(0,len(data),65536):
   chunk=data[off:off+65536];lease=self.pool.acquire(off,len(chunk),p.now*FS_NS);d=self.link.issue('D2H',p.now*FS_NS,chunk,lease);p.sync(ceildiv(d['arrival_fs'],FS_NS),label+':D2H_arrive');end=self.dma.serve('DMA_host_write',p.now*FS_NS,len(chunk));p.sync(ceildiv(end,FS_NS),label+':host_commit');self.link.commit(d,p.now*FS_NS);self.pool.hold(lease,p.now*FS_NS);self.pool.release(lease,p.now*FS_NS)
  return data,e
 def decode(self,p,r,label):
  data,e=self.export(p,r,label);return self.codec.decode(bf(data)),e
 def encode(self,p,r,out,label):
  data,e=self.export(p,r,label);value=self.codec.round(torch.from_numpy(np.frombuffer(data,dtype='<f4').copy()));self.upload(p,out,blob(value));return value,e
 def project(self,p,xr,x,wr,w,yr,label):
  K=x.numel();N=w.shape[0];assert K%64==N%64==0;p.stage=label
  xt=base.Tensor(x,xr.offset,label+':x',xr.producer);wt=base.Tensor(w,wr.offset,label+':w',wr.producer);yt=base.Tensor(torch.empty(N,dtype=torch.float32),yr.offset,label+':y')
  for n0 in range(0,N,64):
   acc=p.op((64,64),label+':zero64lanes',lambda:torch.zeros((64,64),dtype=torch.float32),[])
   for k0 in range(0,K,64):
    xv,_=p.flatload(xt,np.arange(k0,k0+64),label+':input64');idx=(np.arange(n0,n0+64)[:,None]*K+np.arange(k0,k0+64)[None,:]).reshape(-1);wv,_=p.flatload(wt,idx,label+':weight64x64');xv['remaining']=wv['remaining']=1
    if n0==0 and k0==0:self.reject('%d:%s:tile_early_free'%(p.rank,label),lambda:p.free(wv))
    prod=p.op((64,64),label+':independent_mul4096',lambda:wv['data'].reshape(64,64).T*xv['data'].reshape(64,1),[wv,xv]);xv['remaining']=wv['remaining']=0
    self.sram.append(dict(rank=p.rank,buffers=[xv['id'],wv['id']],event=p.last,done_ns=p.now,scalar_reader_groups=64));p.free(xv,wv)
    new=p.op((64,64),label+':independent_lane_add4096',lambda:acc['data']+prod['data'],[acc,prod]);p.free(acc,prod);acc=new
   for off in [32,16,8,4,2,1]:
    new=p.op((off,64),label+':source_half_tree',lambda off=off:acc['data'][:off]+acc['data'][off:2*off],[acc]);p.free(acc);acc=new
   p.store(yt,acc,np.arange(n0,n0+64),label+':store64');p.free(acc)
   self.mark(p,xr,label+':tile%d'%(n0//64),p.last);self.mark(p,wr,'tile%d'%(n0//64),p.last)
  yr.shadow=yt.data.view(torch.uint8).clone();yr.ready=p.now;yr.producer=yt.producer;self.record(p,yr,yt.data.numpy().tobytes());return yt.data
 def pointwise(self,p,ar,a,br,b,yr,label,op):
  assert a.numel()==b.numel();n=a.numel();at=base.Tensor(a,ar.offset,'a',ar.producer);bt=base.Tensor(b,br.offset,'b',br.producer);yt=base.Tensor(torch.empty(n,dtype=torch.float32),yr.offset,'y')
  for k in range(0,n,64):
   av,_=p.flatload(at,np.arange(k,k+64),label+':a64');bv,_=p.flatload(bt,np.arange(k,k+64),label+':b64');av['remaining']=bv['remaining']=1
   if k==0:self.reject('%d:%s:early_operand_free'%(p.rank,label),lambda:p.free(av))
   out=p.op((64,),label,lambda:av['data']*bv['data'] if op=='mul' else av['data']+bv['data'],[av,bv]);av['remaining']=bv['remaining']=0;self.sram.append(dict(rank=p.rank,buffers=[av['id'],bv['id']],event=p.last,done_ns=p.now));p.free(av,bv);p.store(yt,out,np.arange(k,k+64),label+':store64');p.free(out)
  yr.shadow=yt.data.view(torch.uint8).clone();yr.ready=p.now;yr.producer=yt.producer;self.record(p,yr,yt.data.numpy().tobytes());self.mark(p,ar,'arithmetic',p.last);self.mark(p,br,'arithmetic',p.last);return yt.data
 def save(self):
  dump(self.d/'RESIDENCY.json',self.res);dump(self.d/'TRANSFERS.json',self.transfers);dump(self.d/'LINK_DESCRIPTORS.json',self.link.descriptors);dump(self.d/'LINK_PACKETS.json',self.link.packets);dump(self.d/'PINNED_LIFETIMES.json',self.pool.history);dump(self.d/'HOST_DMA.json',self.dma.rows)
  dump(self.d/'LAST_READERS.json',dict(regions=[dict(rank=k[0],offset=k[1],bytes=v['region'].size,label=v['label'],pending=sorted(v['pending']),retired_ns=v['retired']) for k,v in self.leases.items()],readers=self.readers,SRAM=self.sram));assert not self.pool.live
