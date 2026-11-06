"""Deterministic explicit PCIe proxy; time in integer femtoseconds."""
import hashlib
FS_NS=1000000
def ceildiv(a,b):return (a+b-1)//b
class LeasePool:
 def __init__(self):self.live={};self.history=[];self.sequence=0;self.peak=0
 def acquire(self,offset,size,now):
  if size>65536 or len(self.live)==2:raise BufferError('two pinned DMA windows exhausted or oversized')
  self.sequence+=1;key=self.sequence;self.live[key]=dict(offset=offset,bytes=size,hold_until=None)
  self.peak=max(self.peak,sum(x['bytes'] for x in self.live.values()));self.history.append(dict(action='acquire',id=key,offset=offset,bytes=size,time_fs=now));return key
 def hold(self,key,until):self.live[key]['hold_until']=until
 def release(self,key,now):
  x=self.live[key]
  if x['hold_until'] is None or now<x['hold_until']:raise RuntimeError('window released before final consumer')
  self.history.append(dict(action='release',id=key,bytes=x['bytes'],time_fs=now,hold_until=x['hold_until']));del self.live[key]
class Link:
 def __init__(self):
  self.free={'H2D':0,'D2H':0};self.credits=[[0]*16 for _ in range(4)];self.descriptors=[];self.packets=[];self.sequence=0
 def issue(self,direction,ready,payload,lease):
  if not payload or len(payload)>65536:raise ValueError('one descriptor must contain1..65536 bytes')
  q=self.sequence%4;c=min(range(16),key=lambda c:float('inf') if self.credits[q][c] is None else self.credits[q][c]);available=self.credits[q][c]
  if available is None:raise RuntimeError('uncompleted credit cannot be reused')
  issue=max(ready,available);iommu=issue+20*FS_NS;self.sequence+=1;did=self.sequence
  # Reserve until endpoint commit, not merely end of wire serialization.
  self.credits[q][c]=None
  for off in range(0,len(payload),256):
   n=min(256,len(payload)-off);start=max(iommu,self.free[direction]);service=ceildiv(n*100000000,5504)
   end=start+service;arrival=end+250*FS_NS;self.free[direction]=end
   self.packets.append(dict(descriptor=did,direction=direction,offset=off,bytes=n,start_fs=start,serialize_done_fs=end,arrival_fs=arrival))
  d=dict(id=did,direction=direction,queue=q,credit=c,lease=lease,ready_fs=ready,issue_fs=issue,iommu_done_fs=iommu,
   arrival_fs=arrival,bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),commit_fs=None)
  self.descriptors.append(d);return d
 def commit(self,d,now):
  if now<d['arrival_fs']:raise RuntimeError('endpoint completion before packet arrival')
  assert d['commit_fs'] is None and self.credits[d['queue']][d['credit']] is None
  d['commit_fs']=now;self.credits[d['queue']][d['credit']]=now
def negative_controls():
 checks=[];p=LeasePool();a=p.acquire(0,65536,0);b=p.acquire(65536,65536,0)
 try:p.acquire(131072,1,0)
 except BufferError:checks.append('third_pinned_window_rejected')
 else:raise AssertionError('window overflow')
 try:p.release(a,0)
 except RuntimeError:checks.append('pending_window_release_rejected')
 else:raise AssertionError('early free')
 p.hold(a,10)
 try:p.release(a,9)
 except RuntimeError:checks.append('window_last_consumer_guard')
 else:raise AssertionError('early free2')
 l=Link();d=l.issue('H2D',0,b'x'*256,a)
 try:l.commit(d,d['arrival_fs']-1)
 except RuntimeError:checks.append('early_DMA_completion_rejected')
 else:raise AssertionError('early DMA')
 # All64 credits active;65th cannot silently overwrite a pending descriptor.
 l=Link()
 for i in range(64):l.issue('H2D',0,b'x',i)
 try:l.issue('H2D',0,b'x',65)
 except RuntimeError:checks.append('65th_uncommitted_credit_rejected')
 else:raise AssertionError('credit overflow')
 # Opposite direction uses its own serializer and can begin concurrently.
 l=Link();x=l.issue('H2D',0,b'x'*256,1);y=l.issue('D2H',0,b'x'*256,2)
 assert l.packets[0]['start_fs']==l.packets[1]['start_fs'];checks.append('full_duplex_independent_serializers')
 return checks
