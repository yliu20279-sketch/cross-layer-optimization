"""Epoch-bound, whole-batch metadata publication and dispatch lifetime gate."""
import hashlib,struct
class MetadataGate:
 def __init__(self,epoch,cpu_ready_fs,planes):
  self.epoch=epoch;self.cpu_ready_fs=cpu_ready_fs;self.planes=planes;self.cpu=False;self.done={};self.sram=None;self.dispatched=False;self.log=[]
 def tag(self,epoch):
  if epoch!=self.epoch:raise RuntimeError('stale or wrong metadata epoch')
 def publish_cpu(self,now,epoch):
  self.tag(epoch)
  if now<self.cpu_ready_fs or self.cpu:raise RuntimeError('CPU completion not ready or duplicate')
  self.cpu=True;self.log.append(dict(event='CPU_route_complete',time_fs=now,epoch=epoch))
 def issue(self,plane,now,epoch):
  self.tag(epoch)
  if not self.cpu or now<self.cpu_ready_fs:raise RuntimeError('metadata DMA before CPU route complete')
  if plane not in self.planes:raise RuntimeError('unknown plane')
  return self.planes[plane]
 def commit(self,plane,payload,now,epoch,descriptor):
  self.tag(epoch)
  if not self.cpu or plane in self.done:raise RuntimeError('missing CPU or duplicate plane completion')
  if descriptor['commit_fs'] is None or now<descriptor['commit_fs'] or now<descriptor['arrival_fs']:raise RuntimeError('HB callback not complete')
  if payload!=self.planes[plane]:raise RuntimeError('corrupt or partial metadata plane')
  self.done[plane]=now;self.log.append(dict(event='HB_plane_committed',plane=plane,time_fs=now,descriptor=descriptor['id'],sha256=hashlib.sha256(payload).hexdigest()))
 def read_allowed(self,now):
  if not self.cpu or set(self.done)!=set(self.planes) or now<max(self.done.values()):raise RuntimeError('partial metadata batch cannot be read')
 def publish_sram(self,payload,now,epoch,read_done_fs):
  self.tag(epoch);self.read_allowed(now)
  if now<read_done_fs or payload!=self.planes['IDs']+self.planes['weights']:raise RuntimeError('metadata SRAM fill pending or corrupt')
  self.sram=payload;self.log.append(dict(event='metadata_SRAM_ready',time_fs=now,read_done_fs=read_done_fs))
 def dispatch(self,contexts,now,epoch):
  self.tag(epoch);self.read_allowed(now)
  if self.sram is None or self.dispatched:raise RuntimeError('metadata not visible or duplicate dispatch')
  n=len(contexts);ids=struct.unpack('<'+'q'*(n*8),self.sram[:n*64]);weights=struct.unpack('<'+'H'*(n*8),self.sram[n*64:])
  records=[];epoch_tag=int.from_bytes(hashlib.sha256(epoch.encode()).digest()[:8],'little')
  for row,c in enumerate(contexts):
   chosen=ids[row*8:row*8+8]
   if len(set(chosen))!=8 or any(e<0 or e>=128 for e in chosen):raise RuntimeError('invalid expert IDs')
   for slot,expert in enumerate(chosen):
    #32B fixed descriptor; extra debug source labels stay outside the wire ABI.
    records.append(struct.pack('<IIHBBBBHQQ',row,c['local_token'],expert,slot,expert%16,c['local_token']%16,0,weights[row*8+slot],row*4096,epoch_tag))
  self.dispatched=True;self.log.append(dict(event='dispatch_descriptors_released',time_fs=now,records=len(records)))
  return b''.join(records)
 def can_free_sram(self):
  if not self.dispatched:raise RuntimeError('free before metadata last consumer')
