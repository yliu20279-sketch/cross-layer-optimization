import json,ctypes as C
import numpy as np
from integrated_adapter import FullAdapter as Base,UnifiedKV
class FullAdapter(Base):
 def __init__(self,codec,out,state):
  super().__init__(codec,out,state);self.plan=json.loads((out.parent/'LIFETIME_PLAN.json').read_text());self.observed=[];self.lifetimes=[];self.peak_live=0;self.high_water=32*2**20
 def retire_reader(self,node,zero=False):
  assert not node.get('retired_at'),('read_after_retirement',node['id'])
  now=int(self.um.um_now());raw=self.software(25,b'',32,node['id'],node['allocation_version'],int(zero));address,version,remaining,freed=map(int,raw.view('<u8'))
  assert address==node['offset'] and version==node['allocation_version']
  assert not freed,'release must wait for completed layer/return barrier'
  self.lifetimes.append(dict(kind='zero_reader_commit' if zero else 'last_reader_progress',node=node['id'],version=version,address=address,start=now,complete=int(self.um.um_now()),remaining=remaining,freed=bool(freed)))
 def publish(self,label,t,parents=None):
  i=len(self.nodes);plan=self.plan[i];assert (label,list(t.shape),str(t.dtype),self.phase,self.layer)==(plan['label'],plan['shape'],plan['dtype'],plan['phase'],plan['layer']),('finite_DAG_contract_mismatch',i,label)
  raw=self.software(24,b'',32,t.numel()*t.element_size(),i,plan['readers']);address,version,live,peak=map(int,raw.view('<u8'));self.next=address
  result=super().publish(label,t,parents);node=self.nodes[-1];assert node['offset']==address
  node.update(allocation_version=version,planned_readers=plan['readers'],allocation_bytes=(node['bytes']+31)//32*32,allocation_complete=self.services[-1]['complete']);self.observed.append(0)
  self.peak_live=max(self.peak_live,peak);self.high_water=max(self.high_water,address+node['allocation_bytes'])
  self.lifetimes.append(dict(kind='allocate',node=i,version=version,address=address,bytes=node['allocation_bytes'],complete=node['control_ready'],live_bytes=live))
  if not plan['readers']:self.retire_reader(node,True)
  return result
 def layer_barrier(self,phase,layer):
  start=int(self.um.um_now());raw=self.software(26,b'',32+16*len(self.nodes),len(self.nodes));words=raw.view('<u8');count,live,peak,generation=map(int,words[:4]);done=int(self.um.um_now())
  assert count<=len(self.nodes)
  for j in range(count):
   i,version=map(int,words[4+j*2:6+j*2]);node=self.nodes[i]
   assert not node.get('retired_at') and version==node['allocation_version'] and self.observed[i]==node['planned_readers']
   assert max([node['ready']]+[r['done'] for r in node['readers']])<=start
   node.update(retired_at=done,last_consumer_barrier_start=start,last_consumer_barrier_phase=phase,last_consumer_barrier_layer=layer)
   self.lifetimes.append(dict(kind='release_after_consumer_barrier',node=i,version=version,address=node['offset'],start=start,complete=done))
  self.lifetimes.append(dict(kind='barrier',phase=phase,layer=layer,start=start,complete=done,released=count,live_bytes=live,peak_live_bytes=peak))
 def fetch(self,t,label):
  v=self.find(t)
  if v is not None:assert not v['node'].get('retired_at'),('fetch_retired_node',v['node']['id'],label)
  result=super().fetch(t,label)
  for i,node in enumerate(self.nodes):
   n=len(node['readers'])
   while self.observed[i]<n:
    self.retire_reader(node);self.observed[i]+=1
  return result
 def finish(self,cache):
  self.layer_barrier('final_CPU_return',-1)
  assert len(self.nodes)==len(self.plan)
  for node,plan in zip(self.nodes,self.plan):assert len(node['readers'])==plan['readers'] and node.get('retired_at'),('incomplete_lifetime',node['id'])
  (self.out/'LIFETIME_EVENTS.json').write_text(json.dumps(self.lifetimes,indent=2))
  summary=super().finish(cache);summary.update(HB_extent=self.high_water,activation_peak_live_bytes=self.peak_live,allocation_mode='actual CPU first-fit/refcount services; finite preregistered reader DAG; not unseen-route dynamic planning',dynamic_reclamation=True);return summary
