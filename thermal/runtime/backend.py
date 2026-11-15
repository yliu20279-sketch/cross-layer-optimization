"""Causal V3.5 wave scheduler with runtime NPU OPP and deferred refresh states.

Native NPUSim cycles and newly calibrated native DRAMPower/Ramulator profiles.
Not a persistent full-workload Ramulator command queue or complete AMBER policy.
"""
import csv
import json
import math
import heapq
import re
import subprocess
from collections import defaultdict
from pathlib import Path
import numpy as np
from prepare import ROOT, PREP, dump, writecsv

NAMES=[f'CORE{i}' for i in range(16)]+[f'SRAM{i}' for i in range(16)]+[f'DRAM{i}' for i in range(64)]
FIELDS=['MAC','SRAM_read_access','SRAM_write_access','LBUF_read_access','LBUF_write_access']+[f'bank{i}_read_B' for i in range(4)]+[f'bank{i}_write_B' for i in range(4)]+[f'bank{i}_energy_J' for i in range(4)]+['compute_active_ns','DMA_occupied_ns']

def thermal_bank(c,b): return (c//4*2+b//2)*8+c%4*2+b%2
BANK_INDICES=np.array([[32+thermal_bank(c,b) for b in range(4)] for c in range(16)])

def route(a,b):
    out=[a];x,y=a%4,a//4;xx,yy=b%4,b//4
    while x!=xx:x+=1 if xx>x else -1;out.append(y*4+x)
    while y!=yy:y+=1 if yy>y else -1;out.append(y*4+x)
    return out


def primitive_memory_policy(name):
    """Return the explicit target-lowered attention operand policy.

    Vision heads own distinct K/V tensors but retain each B tile across M-row
    tiles.  Gemma GQA heads share one compact K tensor and one compact V tensor
    across all eight query heads.  Action-prefix K/V is prefetched from the
    request's home partition, so QK/PV consume it from SRAM without another
    local DRAM read.
    """
    match=re.fullmatch(r'(vision|prefix|action)_(qk|pv)_h(\d+)',name)
    if not match:return dict(cache_group=None,skip_b_dram=False)
    family,kind,head=match.groups()
    if family=='vision':group=f'{family}_{kind}_h{head}'
    else:group=f'{family}_{kind}_shared_kv'
    return dict(cache_group=group,skip_b_dram=(family=='action'))

class Plant:
    def __init__(self, initial_C):
        t=PREP/'thermal'
        self.p=subprocess.Popen([str(ROOT/'hotspot_stream'),str(t/'hotspot.config'),str(t/'materials'),str(t/'stack.lcf'),str(initial_C)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    def step(self,power,dt=.001):
        self.p.stdin.write(' '.join(map(str,[dt]+list(power)))+'\n');self.p.stdin.flush()
        while True:
            line=self.p.stdout.readline()
            if not line:raise RuntimeError(self.p.stderr.read())
            if line.startswith('TEMP '):
                t=np.fromstring(line[5:],sep=' ');assert t.shape==(96,) and np.isfinite(t).all();return t
    def close(self):
        self.p.stdin.close();code=self.p.wait(timeout=30);err=self.p.stderr.read()
        self.p.stdout.close();self.p.stderr.close()
        if code:raise RuntimeError(err)

class Memory:
    def __init__(self,scenario,curves):
        self.sc=scenario;self.curves=curves;self.cache={}
        self.cluster=0;self.rate=1;self.issue_time_ns=0.
        self.available_ns=np.zeros(16)
        self.wave_profiles=None
        if scenario['timing'].get('memory_backend')=='native_logical_wave_profiles':
            table=json.loads((PREP/'logical_wave_profiles.json').read_text())
            assert table['status']=='PASS' and table['no_intra_logical_burst_barrier']
            self.wave_profiles=table['profiles']
    def set_context(self,cluster,rate):
        self.cluster=int(cluster);self.rate=int(rate)
    def request_regions(self,key,segments,write,rate):
        """Issue one logical DMA on the selected physical partition.

        Profiles remain bounded-context native measurements, but requests to
        the same partition are now causally serialized.  Waiting time carries
        no bytes or command energy; Engine's ordinary idle accounting covers
        that interval.
        """
        service,a=self.regions(key,segments,write)[int(rate)]
        issue=float(self.issue_time_ns);start=max(issue,float(self.available_ns[self.cluster]))
        self.available_ns[self.cluster]=start+service
        wait=start-issue
        return wait+service,a.copy(),wait
    def regions(self,key,segments,write):
        if key in self.cache:return self.cache[key]
        timing=self.sc['timing'];tx=int(timing['dram_transaction_bytes']);interleave=int(timing['dram_bank_interleave_bytes'])
        vector_segment=int(timing['dram_vector_segment_bytes'])
        entries=[];requested=sum(size for addr,size in segments)
        for addr,size in segments:
            end=(addr+size+tx-1)//tx*tx;p=addr//tx*tx
            while p<end:
                size=min(vector_segment,end-p);bank=np.zeros(4);q=p
                while q<p+size:
                    z=min(p+size,(q//interleave+1)*interleave);bank[(q//interleave)&3]+=z-q;q=z
                entries.append((size,bank));p+=size
        if self.wave_profiles is not None:
            native=self.wave_profiles[json.dumps(key,separators=(',',':'))]
            states={};bank=sum((b for size,b in entries),np.zeros(4))
            for rate,profile in native.items():
                a=np.zeros(19);a[9 if write else 5:13 if write else 9]=bank
                a[13:17]=profile['bank_energy_J']
                ns=profile['ns'];duration=max(ns,requested/self.sc['timing']['sram_dma_B_cycle'])
                if duration>ns:a[13:17]+=self.curves[rate]['idle_W_per_partition']*(duration-ns)*1e-9/4
                a[1 if write else 2]=math.ceil(requested/self.sc['power']['sram_access_bytes']);a[18]=duration
                assert abs(bank.sum()-profile['bytes'])<.1
                states[int(rate)]=(duration,a)
            self.cache[key]=states;return states
        states={}
        for rate,curve in self.curves.items():
            ns=0.;a=np.zeros(19)
            for size,bank in entries:
                v=curve['profiles'][('WRITE' if write else 'READ')+':'+str(size)]
                assert 'per-transaction HB' in curve.get('contract',''), 'Recalibrate native memory profiles before running'
                ns+=v['ns']
                a[9 if write else 5:13 if write else 9]+=bank
                a[13:17]+=bank/size*v['total_J']
            # DMA SRAM port has its own fixed 1GHz reservation.
            duration=max(ns,requested/self.sc['timing']['sram_dma_B_cycle'])
            if duration>ns:a[13:17]+=curve['idle_W_per_partition']*(duration-ns)*1e-9/4
            a[1 if write else 2]=math.ceil(requested/self.sc['power']['sram_access_bytes'])
            a[18]=duration
            states[int(rate)]=(duration,a)
        self.cache[key]=states;return states
    @staticmethod
    def wave_regions(name,shape,w,write,partition_bytes,weight_base=None,
                     workspace_base=4096,include_b=True):
        M,K,N=shape['m'],shape['k'],shape['n'];mi,nj,kk,mt,nt,kt=(w[k] for k in ['mi','nj','kk','mt','nt','kt'])
        A=int(workspace_base);workspace_B=(A+2*M*K+4095)//4096*4096
        # Persistent weights do not consume transient workspace.  The old
        # placement always reserved a second full B matrix before C and used a
        # fixed A=4096, which overlaps any real persistent tensor allocation.
        # A non-default workspace base is the explicit opt-in used by the
        # address-audited bridge.  Preserve the historical A/B/C workspace
        # placement for older prepared traces so their calibrated keys and
        # physical addresses remain bit-for-bit compatible.
        compact_persistent=(weight_base is not None and int(workspace_base)!=4096)
        C=(workspace_B if compact_persistent else
           (workspace_B+2*K*N+4095)//4096*4096)
        assert C+2*M*N<=partition_bytes
        B=workspace_B if weight_base is None else int(weight_base)
        assert 0 <= B and B+2*K*N <= partition_bytes
        a=A+2*(mi*K+kk);b=B+2*(kk*N+nj);c=C+2*(mi*N+nj)
        profile_name=re.sub(r'_h\d+$','_head',name)
        key=(profile_name,write,mt,nt,kt,a%8192,b%8192,c%8192,bool(include_b))
        segments=[]
        def rectangle(base,r,col,stride):
            if col==stride:segments.append((base,r*col*2))
            else:segments.extend((base+i*stride*2,col*2) for i in range(r))
        if write:rectangle(c,mt,nt,N)
        else:
            rectangle(a,mt,kt,K)
            if include_b:rectangle(b,kt,nt,N)
        return key,segments
    def wave(self,name,shape,w,rate,write=False,weight_base=None,
             workspace_base=4096,include_b=True):
        key,segments=self.wave_regions(name,shape,w,write,
            self.sc['timing']['dram_partition_bytes'],weight_base,
            workspace_base,include_b)
        return self.request_regions(key,segments,write,rate)

class Shape:
    """One macro-wave in compute, next in DMA; two SRAM operand slots."""
    def __init__(self,model,name,emit,weight_base=None,workspace_base=4096,
                 b_cache=None):
        self.model=model;self.name=name;self.plan=model.plans[name];self.waves=self.plan['waves'];self.emit=emit
        self.weight_base=weight_base;self.workspace_base=workspace_base
        self.read=0;self.compute=0;self.read_done=set();self.dma=None;self.cpu=None;self.write_pending=None;self.finished=False
        self.cycles=0.;self.phase=0;self.output_id=0
        self.current_macro=(self.waves[0]['mi'],self.waves[0]['nj'])
        self.bounded_output=emit and model.sc['timing'].get('bounded_output_macro',False)
        self.waiting_output=False
        self.event_cursor=0
        self.policy=primitive_memory_policy(name)
        self.b_cache=b_cache if b_cache is not None else set()
    def advance(self,start,end,ratio,rate,emit):
        now=start;out=np.zeros(19)
        if now>=end:return now,out
        self.waiting_output=False
        while now<end-1e-7 and not self.finished:
            if self.cpu is None and self.compute in self.read_done and (self.waves[self.compute]['mi'],self.waves[self.compute]['nj'])==self.current_macro:
                w=self.waves[self.compute];self.cpu=w;self.cycles=0.;self.event_cursor=0
            if self.dma is None:
                if self.write_pending is not None:
                    self.model.memory.issue_time_ns=now
                    w=self.write_pending;duration,a,wait=self.model.memory.wave(
                        self.name,self.plan,w,rate,True,self.weight_base,
                        self.workspace_base)
                    self.dma=[duration,duration,a,True,-1,wait,duration-wait];self.write_pending=None
                elif self.read<len(self.waves) and self.read<=self.compute+1:
                    w=self.waves[self.read]
                    self.model.memory.issue_time_ns=now
                    group=self.policy['cache_group']
                    cache_key=(group,w['nj'],w['kk'],w['nt'],w['kt']) if group else None
                    include_b=(not self.policy['skip_b_dram'] and
                               (cache_key is None or cache_key not in self.b_cache))
                    duration,a,wait=self.model.memory.wave(
                        self.name,self.plan,w,rate,False,self.weight_base,
                        self.workspace_base,include_b)
                    if include_b and cache_key is not None:self.b_cache.add(cache_key)
                    self.dma=[duration,duration,a,False,self.read,wait,duration-wait];self.read+=1
            cpu_left=(self.cpu['compute_cycles']-self.cycles)/ratio if self.cpu is not None and ratio>0 else math.inf
            dma_left=self.dma[0] if self.dma else math.inf
            dt=min(end-now,cpu_left,dma_left)
            assert dt>=-1e-6
            dt=max(0.,dt)
            if self.cpu is not None and ratio>0:
                left=self.cycles;right=left+dt*ratio
                events=self.cpu['events']
                begin=self.event_cursor if self.model.sc['timing'].get('event_cursor_optimization',True) else 0
                for event_index in range(begin,len(events)):
                    e=events[event_index]
                    if e[0]>=right:break  # Single native MAC array: events are time ordered.
                    overlap=max(0.,min(right,e[1])-max(left,e[0]))
                    if overlap:
                        out[:5]+=np.asarray(e[2:7])*overlap/(e[1]-e[0]);out[17]+=overlap/ratio
                    if self.emit and e[7] and left<e[1]<=right:
                        ready=now+(e[1]-left)/ratio
                        emit(ready,int(e[7]),int(e[8]));self.output_id+=1
                    if e[1]<=right:self.event_cursor=event_index+1
                self.cycles=right
            if self.dma:
                waiting=min(dt,self.dma[5]);self.dma[5]-=waiting
                service_dt=dt-waiting
                if service_dt:
                    out+=self.dma[2]*(service_dt/self.dma[6])
                self.dma[0]-=dt
            now+=dt
            if self.cpu is not None and self.cycles>=self.cpu['compute_cycles']-1e-6:
                w=self.cpu;self.read_done.remove(self.compute);self.compute+=1;self.cpu=None
                if w['kk']+w['kt']==self.plan['k']:self.write_pending=w
            if self.dma and self.dma[0]<=1e-6:
                if self.dma[3]:
                    if self.compute==len(self.waves):self.finished=True
                    else:
                        self.current_macro=(self.waves[self.compute]['mi'],self.waves[self.compute]['nj'])
                        if self.bounded_output:self.waiting_output=True
                else:self.read_done.add(self.dma[4])
                self.dma=None
            if self.waiting_output:break  # Next macro reuses output space only after NoC drains.
            if dt==0 and not self.finished:raise RuntimeError('Zero-progress wave state')
        return now,out

class Generic:
    def __init__(self,model,task,whole,request_slot=0):
        self.m=model;self.task=task;self.request_slot=request_slot;self.stage=0 if whole else 1;self.whole=whole;self.finished=False;self.left=None;self.full=None;self.a=None;self.wait=0.;self.service_full=0.
        ep=model.streamable.get(task['op'],0)*(task['write_bytes']//2) if not whole else 0
        activity=model.sc['activity_model']
        self.work=(math.ceil((task['vector_ops']-ep)/activity['vector_ops_per_cycle_per_cluster'])+
                   math.ceil(task['reduce_ops']/activity['reduce_ops_per_cycle_per_cluster']))
        # A whole non-GEMM operator consumes its declared tensors.  For a
        # lowered task, GEMM operand/weight accesses already come from native
        # NPUSim events; charging semantic read_bytes here would count weights
        # twice.  Only the remaining vector/reduction scalar activity belongs
        # here.  The MODELED per-op access contract is centralized in the
        # scenario; terminal streaming epilogues are charged by native_plan.
        if whole:
            read_bytes,write_bytes=task['read_bytes'],task['write_bytes']
        else:
            ops=task['vector_ops']-ep+task['reduce_ops']
            assert ops>=0 and activity['generic_scalar_bytes']==4
            read_bytes=ops*activity['generic_reads_per_scalar_op']*activity['generic_scalar_bytes']
            write_bytes=ops*activity['generic_writes_per_scalar_op']*activity['generic_scalar_bytes']
        self.activity_bytes=(read_bytes,write_bytes)
        sram_width=model.sc['power']['sram_access_bytes'];lbuf_width=model.sc['power']['lbuf_access_bytes']
        self.counts=np.array([0,math.ceil(read_bytes/sram_width),math.ceil(write_bytes/sram_width),
                              math.ceil(read_bytes/lbuf_width),math.ceil(write_bytes/lbuf_width)],float)
    def advance(self,start,end,ratio,rate,emit):
        now=start;out=np.zeros(19)
        while now<end-1e-7 and not self.finished:
            if self.left is None:
                if self.stage==1:
                    self.full=max(1,self.work);self.a=np.zeros(19);self.a[:5]=self.counts
                    self.wait=0.;self.service_full=self.full
                else:
                    write=self.stage==2;size=self.task['write_bytes' if write else 'read_bytes']
                    self.m.memory.issue_time_ns=now
                    prefix='write' if write else 'read'
                    slot=self.request_slot
                    if self.task.get(prefix+'_slot_policy')=='partition_striped':
                        slot//=16
                    address=(int(self.task.get(prefix+'_base',4096))+
                             slot*int(self.task.get(prefix+'_slot_stride',0)))
                    # Existing workloads retain their calibrated three-field
                    # key.  Address-aware bridges opt in with an explicit base
                    # (and are calibrated with the address residue included).
                    explicit=(prefix+'_base' in self.task or prefix+'_slot_stride' in self.task)
                    key=('generic',write,size,address%8192) if explicit else ('generic',write,size)
                    self.full,self.a,self.wait=self.m.memory.request_regions(
                        key,[(address,size)],write,rate)
                    self.service_full=self.full-self.wait
                    if self.full==0:
                        self.stage+=1
                        if self.stage==3:self.finished=True
                        continue
                self.left=self.full
            speed=ratio if self.stage==1 else 1.
            if speed==0:return end,out
            dt=min(end-now,self.left/speed);amount=dt*speed
            if self.stage==1:
                out+=self.a*(amount/self.full);out[17]+=dt
            else:
                waiting=min(dt,self.wait);self.wait-=waiting
                service_dt=dt-waiting
                if service_dt:out+=self.a*(service_dt/self.service_full)
            self.left-=amount;now+=dt
            if self.left<1e-6:
                self.stage+=1;self.left=None
                if self.stage==3 or (not self.whole and self.stage==2):self.finished=True
        return now,out

class Task:
    def __init__(self,model,key,start,request_slot=0):
        self.m=model;self.key=key;self.t=model.tasks[key[1]];self.start=start;self.ready=start
        self.request_slot=request_slot
        bases=model.weight_layout.get(str(key[1]),[None]*len(model.lowering.get(self.t['op'],[])))
        self.workspace_base=model.workspace_layout.get(str(key[1]),4096) if hasattr(model,'workspace_layout') else 4096
        self.parts=[('generic',not bool(model.lowering.get(self.t['op'])),None)]+[(s[0],False,bases[i]) for i,s in enumerate(model.lowering.get(self.t['op'],[]))]
        self.b_cache=set()
        self.index=0;self.part=None;self.finished=False;self.totals=np.zeros(19)
    def advance(self,start,end,ratio,rate,emit):
        now=max(start,self.ready);out=np.zeros(19)
        while now<end-1e-7 and not self.finished:
            if self.part is None:
                name,whole,weight_base=self.parts[self.index]
                # Compact attention B tiles live only for the phase that can
                # actually reuse them.  Prefix GQA keeps one K (or V) across
                # its eight query heads, but K is dead when PV begins.  Vision
                # heads do not share K/V with another head, so their entries
                # are retired as each primitive finishes below.  This makes
                # the logical cache lifetime match the capacity audit instead
                # of accumulating dead cache keys for the whole task.
                if re.fullmatch(r'(prefix|action)_pv_h0',name):
                    self.b_cache.difference_update(
                        key for key in tuple(self.b_cache)
                        if key[0] in ('prefix_qk_shared_kv','action_qk_shared_kv'))
                self.part=(Generic(self.m,self.t,whole,self.request_slot)
                           if name=='generic' else
                           Shape(self.m,name,
                                 self.index==len(self.parts)-1 and self.t['op'] in self.m.streamable,
                                 weight_base,self.workspace_base,self.b_cache))
            now,a=self.part.advance(now,end,ratio,rate,emit);out+=a
            if self.part.finished:
                if isinstance(self.part,Shape):
                    group=self.part.policy['cache_group']
                    if group and group.startswith('vision_'):
                        self.b_cache.difference_update(
                            key for key in tuple(self.b_cache) if key[0]==group)
                self.index+=1;self.part=None
                if self.index==len(self.parts):self.finished=True
            else:break
        self.totals+=out
        return now,out

class Model:
    def __init__(self):
        self.sc=json.loads((ROOT/'modeled_scenario.json').read_text())
        w=json.loads((PREP/'workload.json').read_text());self.tasks={t['task_id']:t for t in w['tasks']};self.lowering=w['LOWERING'];self.streamable=w['STREAMABLE']
        self.plans=json.loads((PREP/'native_plan.json').read_text())
        layout=json.loads((PREP/'weight_layout.json').read_text())
        assert layout['status']=='PASS' and layout['partition_bytes']==self.sc['timing']['dram_partition_bytes']
        self.weight_layout=layout['task_primitive_bases']
        self.resident_weight_pairs={(row['weight_set'],int(row['partition']))
            for row in layout['records'] if row['kind']=='task_weight'}
        for p in self.plans.values():
            assert sum(e[2] for w in p['waves'] for e in w['events'])==p['mac_ops']
            assert all(all(a[1]<=b[0] for a,b in zip(w['events'],w['events'][1:])) for w in p['waves'])
            # Original primitive pipeline charge, on first resident-compute wave.
            first=p['waves'][0];shift=p['pipeline_cycles']
            first['compute_cycles']+=shift
            for e in first['events']:e[0]+=shift;e[1]+=shift
        # The C++ planner owns streaming epilogue cycles and accesses.  Keep
        # its hard event contract synchronized with the Python task lowering.
        for task in self.tasks.values():
            if task['op'] not in self.streamable:continue
            terminal=self.lowering[task['op']][-1][0]
            expected=self.streamable[task['op']]*(task['write_bytes']//2)
            assert self.plans[terminal]['epilogue_scalar_ops']==expected
        self.memory=Memory(self.sc,json.loads((PREP/'memory_curves.json').read_text()))
        self.children={t:[] for t in self.tasks}
        for tid,t in self.tasks.items():
            for d in t['deps']:self.children[d].append(tid)

class Engine:
    def __init__(self,model):
        self.m=model;self.sc=model.sc;self.time=0.;self.active={};self.pending=[];self.arrivals=[];self.arrival_seq=0;self.done={};self.links={};self.flows=[];self.pulses=[];self.memory_pulses=[];self.tiles=[];self.prefetch={};self.buffer=np.zeros(16)
        self.memory_available=np.zeros(16)
        self.temperature=np.full(96,self.sc['thermal']['initial_C']);self.f=np.ones(16);self.dtm=np.zeros(16,bool);self.log=[];self.requests={};self.request_slots={};self.transitions=0
    def cluster_for(self,request,task_id):
        """Capacity-checked physical placement for one request task."""
        task=self.m.tasks[task_id];base=task['primary_cluster']
        if task.get('dynamic_home_by_request'):
            slot=self.request_slots.get(request,request%16)
            return slot%16
        mode=self.sc['experiment'].get('request_cluster_placement','static')
        if mode=='static':return base
        # Placement repeats for every cohort.  The global request id is only a
        # trace identity; using it here would change the spatial workload from
        # one thermal-convergence cohort to the next.
        slot=self.request_slots.get(request,request%16)
        if mode=='cyclic_rotation':destination=(base+slot)%16
        if mode=='balanced_rotation':
            slot%=16
            offset=2*slot if slot<8 else 2*(slot-8)+1
            destination=(base+offset)%16
        elif mode!='cyclic_rotation':
            raise ValueError('Unknown request_cluster_placement: '+str(mode))
        weight_set=task.get('weight_set')
        if weight_set and (weight_set,destination) not in self.m.resident_weight_pairs:
            raise RuntimeError('placement requires an unmodeled resident weight copy: '
                               f'{weight_set} -> partition {destination}')
        return destination
    def add_cohort(self,count):
        assert not self.pending and not self.active and not self.arrivals and not self.pulses and not self.memory_pulses
        base=len(self.requests)
        for slot,q in enumerate(range(base,base+count)):
            self.requests[q]=self.time;self.request_slots[q]=slot
            self.pending.extend((q,tid) for tid in self.m.tasks)
    def finished(self):return not self.pending and not self.active and not self.arrivals and not self.pulses and not self.memory_pulses
    def transfer(self,src,dst,amount,ready,key,producer,tile=-1):
        if src==dst:return ready
        path=route(src,dst);links=list(zip(path,path[1:]));timing=self.sc['timing']
        flits=math.ceil(amount/timing['noc_flit_bytes'])
        cycle=timing['noc_cycle_ns'];serialization=flits*cycle
        hop_offset=(timing['noc_link_latency_cycles']+
                    timing['noc_router_pipeline_cycles'])*cycle
        # Wormhole/pipelined reservation: each directed physical link carries
        # the packet for ``flits`` cycles at its own hop offset.  The previous
        # implementation locked every link from injection until tail arrival,
        # suppressing legal link-level overlap.
        start=max([ready]+[self.links.get(link,0.)-index*hop_offset
                           for index,link in enumerate(links)])
        for index,link in enumerate(links):
            self.links[link]=start+index*hop_offset+serialization
        end=(start+serialization+len(links)*timing['noc_link_latency_cycles']*cycle+
             len(path)*timing['noc_router_pipeline_cycles']*cycle)
        p=self.sc['power'];e=np.zeros(96)
        for r in path[:-1]:e[r]+=flits*p['router_pJ_flit_hop']*1e-12
        for r in [src,dst]:e[r]+=flits*p['ni_pJ_endpoint_flit']*1e-12
        self.pulses.append((start,end,e))
        self.flows.append(dict(request=key[0],task_id=key[1],producer=producer,tile=tile,src=src,dst=dst,bytes=amount,ready_ns=ready,start_ns=start,end_ns=end,hops=len(links)))
        return end
    def prefetch_kv(self,key,dst,rates):
        task=self.m.tasks[key[1]]
        if 'kv_layer' not in task:return self.time
        slot=self.request_slots.get(key[0],key[0]%16);home=slot%16
        local_slot=slot//16;size=int(task['kv_layer_bytes'])
        address=(int(task['kv_home_base'])+
                 local_slot*int(task['kv_home_slot_stride'])+
                 int(task['kv_layer'])*size)
        self.m.memory.set_context(home,int(rates[home]))
        self.m.memory.issue_time_ns=self.time
        profile_key=('kv_remote',False,size,address%8192)
        duration,a,wait=self.m.memory.request_regions(
            profile_key,[(address,size)],False,int(rates[home]))
        # Source SRAM is filled by the DRAM DMA (already a[2]) and then read by
        # the NI.  A remote destination receives one SRAM write before the
        # attention primitives consume the compact K/V from SRAM.
        width=int(self.sc['power']['sram_access_bytes'])
        a[1]+=math.ceil(size/width)
        finish=self.time+duration
        self.memory_pulses.append((self.time+wait,finish,home,a))
        flow_end=self.transfer(home,dst,size,finish,key,-2-int(task['kv_layer']))
        if home!=dst:
            endpoint=np.zeros(19);endpoint[2]=math.ceil(size/width)
            start=self.flows[-1]['start_ns']
            self.memory_pulses.append((start,flow_end,dst,endpoint))
        return flow_end
    def step(self,forced_frequency=None,forced_refresh=None):
        # A Model may be used by two audit engines; partition queue state is an
        # Engine property, while immutable native profiles remain shared.
        if hasattr(self.m.memory,'available_ns'):
            self.m.memory.available_ns=self.memory_available
        dt=float(self.sc['timing'].get('scheduler_quantum_ns',1e6));dt_s=dt*1e-9
        assert 0<dt<=1e6
        end=self.time+dt;ctl=self.sc['control'];old=self.f.copy()
        regions=np.maximum(self.temperature[:16],self.temperature[16:32])
        control_enabled=bool(self.sc['experiment'].get('thermal_control_enabled',False))
        self.dtm|=regions>=ctl['thermal_limit_C'];self.dtm&=regions>ctl['release_C']
        if forced_frequency is not None:self.f=np.full(16,forced_frequency)
        elif control_enabled:self.f=np.where(regions>=ctl['thermal_limit_C'],0.,np.where(self.dtm,.5,1.))
        else:self.f=np.ones(16)
        assert all(f in [0]+ctl['opp_ratios'] for f in self.f)
        rates=np.asarray(ctl['refresh_multipliers'])[np.searchsorted(ctl['refresh_thresholds_C'],self.temperature[BANK_INDICES].max(1),side='right')]
        if forced_refresh is not None:rates[:]=forced_refresh
        used=set(self.active)
        # Promote data-ready jobs without reserving an array while their NoC
        # or remote-KV prefetch is still in flight.
        remaining=[]
        for ready,sequence,key in sorted(self.arrivals):
            c=self.cluster_for(*key)
            if ready<=self.time+1e-7 and c not in used and self.f[c]>0 and self.buffer[c]<=self.time:
                start=max(self.time,ready)
                self.active[c]=Task(self.m,key,start,self.request_slots.get(key[0],key[0]%16));used.add(c)
            else:remaining.append((ready,sequence,key))
        self.arrivals=remaining
        queued=np.bincount([self.cluster_for(*item[2]) for item in self.arrivals],minlength=16)
        max_prefetch=int(self.sc['timing'].get('max_prefetched_tasks_per_cluster',2))
        for key in self.pending.copy():
            t=self.m.tasks[key[1]];c=self.cluster_for(*key)
            if self.f[c]==0:continue
            if not all((key[0],d) in self.done for d in t['deps']):continue
            remote=any(self.cluster_for(key[0],dep)!=c for dep in t['deps']) or 'kv_layer' in t
            if c in used and not remote:continue
            if remote and queued[c]>=max_prefetch:continue
            ready=self.time
            for dep in t['deps']:
                src=self.cluster_for(key[0],dep);cache=(key[0],dep,key[1])
                if src!=c and self.m.tasks[dep]['op'] in self.m.streamable:
                    assert cache in self.prefetch;ready=max(ready,self.prefetch[cache])
                else:ready=max(ready,self.transfer(src,c,max(self.sc['timing']['noc_flit_bytes'],self.m.tasks[dep]['write_bytes']),self.time,key,dep))
            ready=max(ready,self.prefetch_kv(key,c,rates))
            if ready<=self.time+1e-7 and c not in used and self.buffer[c]<=self.time:
                self.active[c]=Task(self.m,key,self.time,self.request_slots.get(key[0],key[0]%16));used.add(c)
            else:
                self.arrival_seq+=1;self.arrivals.append((ready,self.arrival_seq,key));queued[c]+=1
            self.pending.remove(key)
        activity=np.zeros((16,19));ready_events=[]
        for c,job in list(self.active.items()):
            if hasattr(self.m.memory,'set_context'):self.m.memory.set_context(c,int(rates[c]))
            changed=old[c]!=self.f[c];self.transitions+=int(changed)
            start=self.time
            if isinstance(job.part,Shape) and job.part.waiting_output:
                start=max(start,self.buffer[c])
            # Transition freezes compute only; memory continues. Sub-window split.
            def emit(at,size,tile,key=job.key,src=c):ready_events.append((at,key,src,size,tile))
            if changed:
                stop=min(end,start+ctl['transition_stall_ns']);_,a=job.advance(start,stop,0.,int(rates[c]),emit);activity[c]+=a;start=stop
            finish,a=job.advance(start,end,float(self.f[c]),int(rates[c]),emit);activity[c]+=a
            if job.finished:
                if self.sc['timing'].get('stream_generic_outputs',False) and job.t['op'] in self.m.streamable and not self.m.lowering.get(job.t['op']):
                    emit(finish,job.t['write_bytes'],-1)
                self.done[job.key]=finish;self.log.append(dict(request=job.key[0],task_id=job.key[1],cluster=c,start_ns=job.start,end_ns=finish,MAC=job.t['mac_ops'],
                    executed_MAC=float(job.totals[0]),physical_read_bytes=float(job.totals[5:9].sum()),physical_write_bytes=float(job.totals[9:13].sum()),
                    compute_active_ns=float(job.totals[17]),DMA_occupied_ns=float(job.totals[18])))
                assert abs(job.totals[0]-job.t['mac_ops'])<max(1,job.t['mac_ops']*1e-9)
                del self.active[c]
        keep_memory=[]
        for start,finish,c,a in self.memory_pulses:
            fraction=max(0.,min(end,finish)-max(self.time,start))/(finish-start)
            activity[c]+=a*fraction
            if finish>end:keep_memory.append((start,finish,c,a))
        self.memory_pulses=keep_memory
        for at,key,src,size,tile in sorted(ready_events):
            for child in self.m.children[key[1]]:
                dst=self.cluster_for(key[0],child)
                if src==dst:continue
                finish=self.transfer(src,dst,size,at,(key[0],child),key[1],tile)
                cache=(key[0],key[1],child);self.prefetch[cache]=max(self.prefetch.get(cache,0.),finish);self.buffer[src]=max(self.buffer[src],finish)
        activity_model=self.sc['activity_model'];peak=activity_model['peak_fp16_MAC_per_cycle_per_cluster'];frequency=activity_model['npu_frequency_Hz']
        assert activity[:,0].max()<=peak*frequency*dt_s+1
        assert activity[:,18].max()<=dt+.01 and activity[:,17].max()<=dt+.01
        power=self.sc['power'];energy=np.zeros(96);components=np.zeros(8)
        v=np.asarray(ctl['voltage_ratios'])[np.searchsorted(ctl['opp_ratios'],self.f)]*(self.f>0)
        core=power['core_static_W']*dt_s+activity[:,0]/(peak*frequency)*power['core_dynamic_full_W']*v*v
        sram=power['sram_leak_W']*dt_s+(activity[:,1]*power['sram_read_pJ_access']+activity[:,2]*power['sram_write_pJ_access'])*1e-12
        lbuf=power['lbuf_leak_W']*dt_s+(activity[:,3]*power['lbuf_read_pJ_access']+activity[:,4]*power['lbuf_write_pJ_access'])*1e-12
        assert power['hb_energy_placement']=='CORE_logic_endpoint'
        hb=activity[:,5:13].sum(1)*8*power['hb_pJ_per_bit']*1e-12
        static_router=power['router_static_W']*dt_s;static_ni=power['ni_static_W']*dt_s
        transition=(old!=self.f)*ctl['transition_energy_J']
        energy[:16]=core+lbuf+hb+static_router+static_ni+transition;energy[16:32]=sram
        idle_W=np.array([self.m.memory.curves[str(r)]['idle_W_per_partition'] for r in rates])
        idle=idle_W*np.maximum(0.,dt-activity[:,18])*1e-9
        energy[BANK_INDICES]=activity[:,13:17]+idle[:,None]/4
        components=np.array([core.sum(),sram.sum(),lbuf.sum(),16*static_router,16*static_ni,hb.sum(),activity[:,13:17].sum()+idle.sum(),transition.sum()])
        keep=[]
        for start,finish,e in self.pulses:
            fraction=max(0.,min(end,finish)-max(self.time,start))/(finish-start)
            energy+=e*fraction
            if finish>end:keep.append((start,finish,e))
        network_dynamic=energy.sum()-components.sum()
        # Router/NI split independently from current overlapping flow reservations.
        router=ni=0.
        for flow in self.flows[self._flow_start if hasattr(self,'_flow_start') else 0:]:
            if flow['end_ns']<=self.time:continue
            overlap=max(0.,min(end,flow['end_ns'])-max(self.time,flow['start_ns']))/(flow['end_ns']-flow['start_ns'])
            flits=math.ceil(flow['bytes']/self.sc['timing']['noc_flit_bytes'])
            router+=flits*flow['hops']*power['router_pJ_flit_hop']*1e-12*overlap
            ni+=flits*2*power['ni_pJ_endpoint_flit']*1e-12*overlap
        self._flow_start=next((i for i in range(getattr(self,'_flow_start',0),len(self.flows)) if self.flows[i]['end_ns']>end),len(self.flows))
        components[3]+=router;components[4]+=ni
        assert abs(network_dynamic-router-ni)<1e-10
        assert energy.min()>=0 and abs(energy.sum()-components.sum())<1e-10
        self.pulses=keep;self.time=end;self.last_activity=activity;self.last_components=components;self.last_rates=rates
        return energy/dt_s
