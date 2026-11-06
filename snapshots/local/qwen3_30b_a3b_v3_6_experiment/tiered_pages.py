"""Exclusive host/HB page migration reference state machine.

This module is not an integrated LegoSim performance result. Transfers use
the frozen PCIe throughput proxy, with explicit staging and no prefetch.
"""
from collections import OrderedDict
import math

class TieredPages:
    def __init__(self, pages_by_rank, slots, page_bytes, host_bytes,
                 gbps=55.04, latency_ns=250):
        if slots<1 or page_bytes<1 or gbps<=0: raise ValueError('invalid geometry')
        self.page_bytes=page_bytes; self.host_capacity=host_bytes
        self.gbps=gbps; self.latency=latency_ns; self.slots=slots
        self.caches=[OrderedDict() for _ in pages_by_rank]; self.host=set()
        self.owner={}; self.clock={'H2D':0,'D2H':0}; self.transfers=[]
        self.hits=self.misses=self.evictions=0
        for rank,pages in enumerate(pages_by_rank):
            for i,page in enumerate(pages):
                if page in self.owner: raise ValueError('duplicate page')
                self.owner[page]=rank
                if i<slots: self.caches[rank][page]=True
                else: self.host.add(page)
        self.validate()

    def validate(self):
        resident=set()
        for rank,cache in enumerate(self.caches):
            assert len(cache)<=self.slots
            for page in cache:
                assert self.owner[page]==rank and page not in resident
                resident.add(page)
        assert not resident & self.host
        assert resident | self.host == set(self.owner)
        assert len(self.host)*self.page_bytes<=self.host_capacity

    def transfer(self,direction,ready,page):
        start=max(ready,self.clock[direction])
        service=math.ceil(self.page_bytes/self.gbps)
        self.clock[direction]=start+service
        done=self.clock[direction]+self.latency
        self.transfers.append(dict(page=page,direction=direction,ready=ready,start=start,service_cycles=service,done=done,bytes=self.page_bytes))
        return done

    def access(self,page,ready=0):
        rank=self.owner[page]; cache=self.caches[rank]
        if page in cache:
            self.hits+=1; cache.move_to_end(page); return ready
        self.misses+=1
        # H2D first lands in the explicitly reserved staging buffer. This
        # frees a host slot before the victim is returned in the D2H phase.
        staged=self.transfer('H2D',ready,page); self.host.remove(page)
        done=staged
        if len(cache)==self.slots:
            victim,_=cache.popitem(last=False); self.evictions+=1
            done=self.transfer('D2H',staged,victim); self.host.add(victim)
        cache[page]=True; self.validate(); return done

def selftest():
    p=TieredPages([['a','b','c']],1,256,512,gbps=1,latency_ns=10)
    assert p.access('a',5)==5
    assert p.access('b',5)==537
    assert p.host=={'a','c'} and list(p.caches[0])==['b']
    assert p.access('b',600)==600 and p.hits==2
    p.access('c',600); p.validate(); assert p.evictions==2
    for direction in ('H2D','D2H'):
        records=[r for r in p.transfers if r['direction']==direction]
        for a,b in zip(records,records[1:]): assert b['start']>=a['start']+a['service_cycles']
    try: TieredPages([['a','b','c']],1,256,255)
    except AssertionError: pass
    else: raise AssertionError('capacity overflow accepted')
    q=TieredPages([['a'],['b']],1,256,0); q.validate()
    return {'status':'PASS','checks':['exclusive ownership','LRU replacement','host overflow rejected','directional link serialization','staging transfer sequence','warm hit has no transfer'], 'limitations':['reference state machine only; not coupled to LegoSim','cold placement must be separately compared with warm steady state','page-sized staging must fit runtime reserve','queue and packet effects are not modeled by this throughput reference']}

if __name__=='__main__':
    import json
    print(json.dumps(selftest(),indent=2))
