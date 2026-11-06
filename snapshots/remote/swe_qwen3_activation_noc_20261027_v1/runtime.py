import ctypes as C,hashlib,json,os,select,subprocess
from pathlib import Path
import numpy as np
import torch
B=Path('/mnt/sda1/h3240101068');MULTI=B/'olmoearth_v3_6_multi_npu_20261025_v1';OLD=B/'olmoearth_v3_6_integration_20261025_v1'
import sys
sys.path.insert(0,str(OLD));import run_integrated as base
def digest(v):return hashlib.sha256(v).hexdigest()
def bind(rank):
 lib=C.CDLL(str(MULTI/('libolmo_native_%02d.so'%rank)),mode=C.RTLD_LOCAL);U=C.c_uint64;P=C.POINTER(U)
 lib.ob_init.argtypes=[C.c_char_p];lib.ob_init.restype=C.c_int;lib.ob_error.restype=C.c_char_p
 lib.ob_step.argtypes=[U,C.c_int,U,U,P,P,C.c_int,P,C.c_int,U,P];lib.ob_step.restype=C.c_int
 lib.ob_now.restype=U;lib.ob_requests.restype=U;return lib
class Region:
 def __init__(self,owner,offset,size,label):
  self.owner=owner;self.offset=offset;self.size=size;self.label=label;self.shadow=None;self.ready=None;self.producer=0;self.retired=False
 @property
 def global_address(self):return (self.owner<<29)+self.offset
class Peer(base.Runtime):
 def __init__(self,rank,out):
  self.rank=rank;base.bind=lambda:bind(rank);base.OUT=out/('N%02d'%rank);base.OUT.mkdir();super().__init__()
  self.stage='activation_metadata_NoC';self.regions=[];self.receivenext=1048576;self.hbpeak=0
 def region(self,offset,size,label):
  assert offset%32==0 and offset+size<=536870912
  assert all(offset+size<=r.offset or offset>=r.offset+r.size for r in self.regions)
  r=Region(self.rank,offset,size,label);self.regions.append(r);self.hbpeak=max(self.hbpeak,offset+size);return r
 def inbox(self,size,label):
  p=self.region(self.receivenext,size,label);self.receivenext+=(size+31)//32*32;return p
 def sync(self,t,label):self.event(7,label,delay=max(0,int(t)-self.now))
 def stage_bytes(self,payload,label):
  b=self.alloc((len(payload),),torch.uint8,label);self.service(0,len(payload),label+':fill')
  b.update(data=torch.from_numpy(np.frombuffer(payload,dtype='u1').copy()),ready=self.now,producer=self.last);return b
 def store_bytes(self,r,b,label):
  if r.owner!=self.rank:raise RuntimeError('remote HB bypass')
  guard=getattr(r,'activation_guard',None)
  if guard is not None and (not r.retired or guard.readers!=set(range(8))):raise RuntimeError('activation overwrite before last-reader retirement')
  self.need(b);assert b['bytes']==r.size;self.service(b['bytes'],0,label+':drain')
  self.event(1,label,byte_count=r.size,segments=[(r.offset,r.size)],deps=[b['producer']])
  r.shadow=b['data'].clone();r.ready=self.now;r.producer=self.last
 def write(self,r,payload,label):
  b=self.stage_bytes(payload,label+':stage')
  try:self.store_bytes(r,b,label)
  finally:self.free(b)
 def free(self,*buffers):
  for b in buffers:
   if 'NoC_hold' in b and (b['NoC_hold'] is None or self.now<b['NoC_hold']):raise RuntimeError('TX free before NoC last-reader')
   if b.get('RX_pending_commit'):raise RuntimeError('RX free before HB commit')
  return super().free(*buffers)
 def load(self,r,label):
  if r.owner!=self.rank:raise RuntimeError('remote HB bypass')
  if r.retired or r.ready is None:raise RuntimeError('activation not resident or already retired')
  b=self.alloc((r.size,),torch.uint8,label)
  self.event(0,label,byte_count=r.size,segments=[(r.offset,r.size)],deps=[r.producer]);read_event=self.last;read_done=self.now
  self.service(0,r.size,label+':fill');b.update(data=r.shadow.clone(),ready=self.now,producer=self.last)
  return b,read_event,read_done
 def finish(self):
  assert not self.live and self.used==0;self.trace.close();self.arena.close()
  assert self.counts['RAM_transactions']==self.lib.ob_requests()
  return dict(rank=self.rank,counts=dict(self.counts),SRAM_peak_bytes=self.peak,HB_address_extent_bytes=self.hbpeak,
   HB_allocated_bytes=sum(r.size for r in self.regions),done_ns=self.now)
class Activation:
 def __init__(self,row,region):self.row=row;self.region=region;self.readers=set();self.events=[];region.activation_guard=self
 def read_done(self,slot,event,when):
  if slot in self.readers or self.region.retired:raise RuntimeError('duplicate or stale activation reader')
  self.readers.add(slot);self.events.append(dict(slot=slot,event=event,done_ns=when))
 def retire(self):
  if self.region.retired or self.readers!=set(range(8)):raise RuntimeError('HB reuse before activation last-reader or duplicate retirement')
  self.region.retired=True
def certificate(lines,first,last,index,nbytes,end):
 group=[r for r in lines if first<=r[0]<last and r[1]==index]
 if len(group)!=nbytes//128 or len({r[0] for r in group})!=len(group):raise RuntimeError('missing or duplicate native packet certificate')
 if end is None or any(r[3]>end for r in group):raise RuntimeError('packet tails not complete')
 return group
class NoC:
 def __init__(self,out):
  self.out=out;self.raw=open(out/'noc.stdout','w');self.err=open(out/'noc.stderr','w')
  env=dict(os.environ,POPNET_COUPLED='1',OLMO_PACKET_TRACE=str(out/'packets.txt'),OLMO_NOC_CAPACITY=str(out/'noc_capacity.json'))
  cmd=[str(MULTI/'noc_bridge_v2'),'-A','4','-c','2','-V','3','-B','8','-O','8','-F','4','-L','2000','-T','1000000000','-r','1','-R','0']
  self.p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err,text=True,env=env,bufsize=1)
  self.pending=b'';self.read('READY');self.now=0;self.packet=0;self.batches=[]
 def read(self,prefix):
  while True:
   while b'\n' not in self.pending:
    if not select.select([self.p.stdout],[],[],30)[0]:raise RuntimeError('NoC response watchdog')
    chunk=os.read(self.p.stdout.fileno(),65536)
    if not chunk:raise RuntimeError('NoC terminated')
    self.pending+=chunk
   line,self.pending=self.pending.split(b'\n',1);s=line.decode(errors='replace')+'\n'
   self.raw.write(s);self.raw.flush()
   if s.startswith(prefix):return s.strip().split()
 def run(self,messages,earliest):
  assert all(s!=d and n%128==0 for s,d,n in messages)
  self.p.stdin.write('B %d %d\n'%(len(messages),max(earliest,self.now))+''.join('%d %d %d\n'%m for m in messages));self.p.stdin.flush()
  x=self.read('RESULT');first,last,now=map(int,x[1:4]);ends=list(map(int,x[4:]));assert first==self.packet and len(ends)==len(messages)
  lines=[tuple(map(float,l.split())) for l in (self.out/'packets.txt').read_text().splitlines()]
  lines=[(int(a),int(b),c,d) for a,b,c,d in lines];subset=[r for r in lines if first<=r[0]<last]
  assert {r[0] for r in subset}==set(range(first,last)) and len(subset)==last-first
  assert all(r[2]>=earliest and r[3]>=r[2] for r in subset)
  for i,(_,_,n) in enumerate(messages):certificate(subset,first,last,i,n,ends[i])
  record=dict(batch=len(self.batches),first=first,last=last,earliest=earliest,now=now,messages=messages,ends=ends)
  self.batches.append(record);self.now=now;self.packet=last;return record,subset
 def close(self):
  self.p.stdin.write('QUIT\n');self.p.stdin.flush();self.p.wait(timeout=15);assert self.p.returncode==0;self.raw.close();self.err.close()
 def abort(self):
  if self.p.poll() is None:self.p.terminate();self.p.wait(timeout=15)
