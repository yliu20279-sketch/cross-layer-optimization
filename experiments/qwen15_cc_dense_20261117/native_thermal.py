"""Drive native OPP admissions with the project's thermal contract controller."""

import csv
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np


class NativeThermal:
    def __init__(self, joint, calibration, case, out, count):
        package = joint / 'thermal_bcbee2c4'
        sys.path.insert(0, str(package / 'src'))
        import portable
        rebuilt = Path(json.loads((joint/'THERMAL_PREPARATION.json').read_text())['kernel'])
        kernel = out / 'thermal_kernel.npz'
        values = json.loads(rebuilt.read_text())
        np.savez(kernel, **{k: np.asarray(v, dtype=float) for k, v in values.items()})
        portable.kernel_path = lambda: kernel
        from graph_scheduler import thermal_bank
        from moe60_controller import Controller
        from op_thermal import ThermalPlant
        self.thermal_bank = thermal_bank
        path = package/'inputs/prepared/operating_point_2ghz_rconv3'
        read = lambda path: json.loads(path.read_text())
        config = read(path/'amber_config.json')
        config['online'].update(thermal_target_C=60., thermal_max_C=65., safety_guard_C=1.)
        scenario = read(path/'scenario.json')
        initial = ThermalPlant(scenario['thermal']['initial_C'],path/'rc').state
        self.curves = read(package/'runtime/prepared/memory_curves.json')['1']['profiles']
        self.controller = Controller(scenario, config, {}, 'contract_energy', initial)
        self.profile = {q:read(calibration/f'opp{q}/RESULT.json')['timing'] for q in (2,3,4)}
        self.power = scenario['power']
        self.work = SimpleNamespace(intervals=[], cursor=0, array_free=[0]*16, partition_free=[0]*16,
                                    profile=self.task_profile)
        self.controller.energy = lambda sim, task, c, p, ratio: self.matrix_energy(task['task_id'], p, round(ratio*4))
        self.origin = None
        self.count = count
        self.gets_observed = False
        self.peak = float(self.controller.temperature.max())
        self.out = out
        (out/'THERMAL_MODEL.json').write_text(json.dumps(dict(case=case, ambient_C=scenario['thermal']['initial_C'],
            scope='native OPP timing plus published RC and modeled activity-to-power coefficients',
            memory='32-byte native transaction counts with published reference energy per transaction',
            sram='occupied bank-service slots bound SRAM accesses', thermal_rc_capacity_GiB=32,
            native_HB_capacity_GiB=8, initial_state='uniform ambient at first dispatch arrival'),indent=2)+'\n')

    def elapsed(self, stamp):
        return stamp - self.origin

    def task_profile(self, task, ratio):
        row = self.profile[round(ratio * 4)][task['task_id']]
        return dict(duration_ns=row['complete'] - row['actual_start'])

    def memory_energy(self, partition, count, write=None):
        energy = np.zeros(96)
        p = self.power
        one = max(self.curves[k]['total_J'] for k in ('READ:32','WRITE:32')) if write is None else \
            self.curves[('WRITE' if write else 'READ')+':32']['total_J']
        for bank in range(4):
            energy[32+self.thermal_bank(partition,bank)] += count*one/4
        energy[partition] += count*32*8*p['hb_pJ_per_bit']*1e-12
        return energy

    def network_energy(self, src, dst, flits):
        energy = np.zeros(96)
        p = self.power
        at = src
        while at != dst:
            energy[at] += flits*p['router_pJ_flit_hop']*1e-12
            if at%4 != dst%4:
                at += 1 if dst%4 > at%4 else -1
            else:
                at += 4 if dst>at else -4
        energy[src] += flits*p['ni_pJ_endpoint_flit']*1e-12
        energy[dst] += flits*p['ni_pJ_endpoint_flit']*1e-12
        return energy

    def matrix_energy(self, index, partition, q):
        ref = self.profile[4][index]
        row = self.profile[q][index]
        assert ref['rank']==row['rank']==partition
        energy = self.memory_energy(partition,row['dram_requests'])
        energy[partition] += (ref['compute_cycles'] * 1e-9 * self.power['core_dynamic_full_W'] *
                              self.controller.voltages[q/4]**2)
        energy[16+partition] += ref['sram_bank_cycles'] * 8 * max(self.power['sram_read_pJ_access'],
                                                               self.power['sram_write_pJ_access']) * 1e-12
        return energy

    def append(self, start, stop, energy):
        if stop>start:
            self.work.intervals.append((start,stop,energy,np.zeros(7)))

    def observe_rpc(self, opcode, args, live, start, end):
        if self.origin is None or start < self.origin or end <= start:
            return
        if opcode in (2,3):
            energy = self.memory_energy(live[args[0]][0],math.ceil(args[2]/32),opcode==2)
        elif opcode==7:
            src,dst = (live[h][0] for h in args[:2])
            count = math.ceil(args[2]/32)
            energy = self.network_energy(src,dst,count)+self.memory_energy(src,count,False)+self.memory_energy(dst,count,True)
        elif opcode==6:
            partition = live[args[0]][0]
            energy = self.memory_energy(partition,3*math.ceil(args[3]*4/32))
            energy[partition] += math.ceil(args[3]/16)*self.power['core_dynamic_full_W']*1e-9
        else:
            return
        self.append(self.elapsed(start),self.elapsed(end),energy)

    def see_gets(self):
        if self.gets_observed:
            return
        with (self.out/'backend/GETS.csv').open() as stream:
            gets = [{k:int(v) for k,v in row.items()} for row in csv.DictReader(stream)]
        assert len(gets)==self.count
        for row in gets:
            self.append(row['request_inject'],row['request_done'],self.network_energy(0,1,1))
            self.append(row['request_done'],row['read_done'],self.memory_energy(1,2,False))
            self.append(row['reply_inject'],row['reply_done'],self.network_energy(1,0,2))
        self.gets_observed = True

    def schedule(self,index,rank,ready):
        self.see_gets()
        task = {'task_id':index}
        c = self.controller
        baseline = float(c.static[rank]+c.static[16+rank]+sum(c.static[32+self.thermal_bank(rank,b)] for b in range(4)))
        q = min((2,3,4),key=lambda q:(self.matrix_energy(index,rank,q).sum()+baseline*self.task_profile(task,q/4)['duration_ns']*1e-9,
                                    self.task_profile(task,q/4)['duration_ns'],-q))
        c.choices[index]=q/4
        self.work.cursor=self.elapsed(ready)
        ratio, _, when = c.choose_opp(self.work,task,rank,rank,self.work.cursor)
        self.peak=max(self.peak,float(c.temperature.max()))
        return round(ratio*4), self.origin+math.ceil(when)

    def commit_matrix(self,index,rank,q,release,done):
        self.append(self.elapsed(release),self.elapsed(done),self.matrix_energy(index,rank,q))

    def finish(self,done):
        self.controller.observe(self.work)
        self.controller.advance(self.elapsed(done))
        self.peak=max(self.peak,float(self.controller.temperature.max()))
        return dict(peak_at_observed_checkpoints_C=self.peak, admitted_bound_C=self.controller.maximum_admitted_bound_C,
                    decisions=self.controller.rows)
