"""Original fixed-XY reservations and power rendering, extracted unchanged.
No configurable-switch/NoC-reconfiguration implementation is included here.
"""
import json
import math
from pathlib import Path
import numpy as np
from backend import route
HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / 'sota_compare_config.json').read_text())
COMPONENTS = ['CORE', 'SRAM', 'LBUF', 'Router', 'NI', 'HB', 'DRAM']
class Network:
    def __init__(self, scenario):
        self.sc = scenario
        self.links = {}
        self.flows = []

    def transfer(self, src, dst, amount, ready, kind, task_key, mode="full_global"):
        amount = int(amount)
        if src == dst or amount <= 0:
            return ready
        path = route(src, dst)
        links = list(zip(path, path[1:]))
        timing = self.sc["timing"]
        flits = math.ceil(amount / timing["noc_flit_bytes"])
        mode_cfg=CFG["hiband"]["noc_modes"].get(mode)
        if mode_cfg is None:raise ValueError("Unknown NoC mode: "+str(mode))
        # The unchanged XY link is time-division multiplexed according to the
        # selected logical mode.  Reserving ceil(flits/share) physical cycles
        # makes the mode affect service while never creating extra bandwidth.
        share=max(float(mode_cfg["local_priority"]),float(mode_cfg["global_priority"]))
        if not 0 < share <= 1:raise ValueError((mode,share))
        serialization_cycles=math.ceil(flits/share)
        cycle=timing["noc_cycle_ns"]
        serialization=serialization_cycles*cycle
        hop_offset=(timing["noc_link_latency_cycles"]+
                    timing["noc_router_pipeline_cycles"])*cycle
        start=max([ready]+[self.links.get(link,0.0)-index*hop_offset
                           for index,link in enumerate(links)])
        for index,link in enumerate(links):
            self.links[link]=start+index*hop_offset+serialization
        end=(start+serialization+len(links)*timing["noc_link_latency_cycles"]*cycle+
             len(path)*timing["noc_router_pipeline_cycles"]*cycle)
        self.flows.append(dict(request=task_key[0], task_id=task_key[1],
                               kind=kind, mode=mode, src=src, dst=dst,
                               bytes=amount, ready_ns=ready, start_ns=start,
                               end_ns=end, queue_ns=start-ready,
                               mode_service_share=share,
                               payload_flit_cycles=flits,
                               arbitration_reservation_cycles=serialization_cycles,
                               hops=len(links), path="-".join(map(str, path))))
        return end

def render_trace(sim, makespan):
    bin_ns=CFG["common"]["power_bin_ns"]; dt=bin_ns*1e-9
    bins=max(1,math.ceil(makespan/bin_ns));energy=np.zeros((bins,96));parts=np.zeros((bins,len(COMPONENTS)))
    def spread(start,end,e,c):
        duration=end-start
        first=int(start//bin_ns)
        last=min(bins,int(math.ceil(end/bin_ns)))
        if last<=first:return
        index=np.arange(first,last)
        overlap=np.maximum(0.0,np.minimum(end,(index+1)*bin_ns)-
                           np.maximum(start,index*bin_ns))
        weight=overlap/duration
        energy[first:last]+=weight[:,None]*e
        parts[first:last]+=weight[:,None]*c
    for start,end,e,c in sim.intervals:spread(start,end,e,c)
    sc=sim.m.sc;p=sc["power"]
    static=np.zeros(96);static[:16]=(p["core_static_W"]+p["lbuf_leak_W"]+
                                      p["router_static_W"]+p["ni_static_W"])
    static[16:32]=p["sram_leak_W"]
    idle=sim.m.memory.curves["1"]["idle_W_per_partition"]
    static[32:]=idle/4
    energy+=static[None,:]*dt
    parts[:,0]+=16*p["core_static_W"]*dt
    parts[:,1]+=16*p["sram_leak_W"]*dt
    parts[:,2]+=16*p["lbuf_leak_W"]*dt
    parts[:,3]+=16*p["router_static_W"]*dt
    parts[:,4]+=16*p["ni_static_W"]*dt
    parts[:,6]+=16*idle*dt
    if abs(energy.sum()-parts.sum())>max(1e-10,energy.sum()*1e-10):
        raise AssertionError((energy.sum(),parts.sum()))
    return energy/dt,parts
