import csv,json,math,collections,runpy
from pathlib import Path
R=Path(__file__).resolve().parent
runpy.run_path(str(R/'audit_full.py'))
counts=[]
for iteration in [1,2]:
 D=R/('case%d'%iteration);clocks=list(csv.DictReader((R/'run1'/('clock_round%d.csv'%iteration)).open()));rows=list(csv.DictReader((D/('domain_service_round%d.csv'%iteration)).open()));n=len((D/'transport_bench.txt').read_text().splitlines());assert len(clocks)==2*n
 by=collections.defaultdict(list);rates=collections.defaultdict(list)
 for v in clocks:
  s,d=int(v['src']),int(v['dst']);rate=float(v['clock_ratio']);ns=float(v['global_ns']);assert (rate in [1.0,2.5] if 48 in [s,d] else rate==1.0) and round(ns*rate)==int(float(v['native_ticks']))
  by[(s,d,int(v['descriptor']))].append(ns);rates[(s,d,int(v['descriptor']))].append(rate)
 grouped=collections.defaultdict(list)
 for v in rows:grouped[(int(v['src']),int(v['dst']),int(v['descriptor']))].append(v)
 for key,vs in grouped.items():
  assert len(by[key])==2*len(vs)
  for i,v in enumerate(vs):assert float(v['ready'])==math.ceil(max(by[key][2*i:2*i+2])) and sorted(rates[key][2*i:2*i+2])==([1.0,2.5] if 48 in key[:2] else [1.0,1.0])
 counts.append(len(clocks))
cfg=json.loads((R/'unified_full.yml').read_text());assert cfg['phase1'][0]['clock_rate']==2.5
assert all(p['args'][2]=='1.25' for p in cfg['phase1'] if p['cmd'].endswith('/ramulator2'))
(R/'CLOCK_AUDIT.json').write_text(json.dumps(dict(state='PASS_LIMITED_FULL_LAYER_CLOCK_BINDING',clock_observations=counts,CPU_clock_rate=2.5,DRAM_tick_ns=1.25,full_steps_1_7=False,remaining='opcode/CPU software/SRAM-bank timing, physical calibration and policies not certified'),indent=2))
