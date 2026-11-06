import json
from lifetime_adapter import FullAdapter as LifetimeBase
from integrated_adapter import FullAdapter as IntegratedBase, UnifiedKV as KVBase

class FullAdapter(LifetimeBase):
 def __init__(self,*args):
  super().__init__(*args);self.owner_events=[];self.owner_pins={}
 def owner_change(self,node,retain,reason,required_ready=0):
  assert not node.get('retired_at')
  start=int(self.um.um_now());assert start>=required_ready
  raw=self.software(27 if retain else 28,b'',32,node['id'],node['allocation_version'])
  address,version,pins,reserved=map(int,raw.view('<u8'))
  prior=self.owner_pins.get(node['id'],0);expected=prior+(1 if retain else -1)
  assert expected>=0 and pins==expected and not reserved
  assert (address,version)==(node['offset'],node['allocation_version'])
  self.owner_pins[node['id']]=pins
  self.owner_events.append(dict(node=node['id'],version=version,retain=retain,reason=reason,pins=pins,start=start,required_ready=required_ready,complete=int(self.um.um_now())))
 def layer_barrier(self,phase,layer):
  super().layer_barrier(phase,layer)
  for i,pins in self.owner_pins.items():
   if pins:assert not self.nodes[i].get('retired_at'),('owned_KV_reclaimed',i)
 def finish(self,cache):
  cache.close()
  self.layer_barrier('final_CPU_return_and_session_close',-1)
  assert len(self.nodes)==len(self.plan)
  for node,plan in zip(self.nodes,self.plan):
   assert len(node['readers'])==plan['readers'] and node.get('retired_at')
  assert not any(self.owner_pins.values())
  raw=self.software(29,b'',32);state=tuple(map(int,raw.view('<u8')))
  assert state==(0,0,0,208*2**20),state
  assert self.um.um_finalize()==0,'native endpoint teardown acknowledgement required'
  (self.out/'LIFETIME_EVENTS.json').write_text(json.dumps(self.lifetimes,indent=2))
  (self.out/'KV_OWNERSHIP_EVENTS.json').write_text(json.dumps(self.owner_events,indent=2))
  (self.out/'ARENA_FINAL.json').write_text(json.dumps(dict(live_nodes=state[0],live_bytes=state[1],pins=state[2],free_bytes=state[3],endpoint_acknowledged=True),indent=2))
  summary=IntegratedBase.finish(self,cache)
  summary.update(HB_extent=self.high_water,activation_peak_live_bytes=self.peak_live,dynamic_reclamation=True,allocation_mode='CPU first-fit; finite preregistered reader DAG plus explicit KV session ownership')
  return summary

class UnifiedKV(KVBase):
 def append(self,session,layer,key,value,positions):
  old=self.entries.get((session,layer))
  old_nodes=[] if old is None else [self.a.find(t)['node'] for t in old]
  result=super().append(session,layer,key,value,positions)
  new_nodes=[self.a.find(t)['node'] for t in result]
  ready=max(n['ready'] for n in new_nodes)
  for node in new_nodes:self.a.owner_change(node,True,'KV_pair_committed',ready)
  for node in old_nodes:self.a.owner_change(node,False,'KV_pair_replaced',ready)
  return result
 def close(self):
  for pair in self.entries.values():
   for t in pair:self.a.owner_change(self.a.find(t)['node'],False,'explicit_session_close')
  self.entries.clear()
