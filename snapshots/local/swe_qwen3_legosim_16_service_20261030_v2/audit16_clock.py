import json,csv,math,collections,runpy
from pathlib import Path
R=Path(__file__).resolve().parent;A=R.parent/'swe_qwen3_legosim_16_service_20261030_v1'
runpy.run_path(str(R/'audit16_v2.py'))
for iteration in [1,2]:
 clocks=list(csv.DictReader((R/'run1'/('clock_round%d.csv'%iteration)).open()));rows=list(csv.DictReader((R/('case%d'%iteration)/('domain_service_round%d.csv'%iteration)).open()))
 assert len(clocks)==2*5648
 by=collections.defaultdict(list)
 for v in clocks:
  s,d=int(v['src']),int(v['dst']);rate=float(v['clock_ratio']);native=float(v['native_ticks']);ns=float(v['global_ns'])
  assert rate==(2.5 if 48 in [s,d] else 1.0) and round(ns*rate)==int(native)
  by[(s,d,int(v['descriptor']))].append(ns)
 grouped=collections.defaultdict(list)
 for v in rows:grouped[(int(v['src']),int(v['dst']),int(v['descriptor']))].append(v)
 for key,vals in grouped.items():
  assert len(by[key])==2*len(vals)
  for i,v in enumerate(vals):assert float(v['ready'])==math.ceil(max(by[key][2*i:2*i+2]))
for rank in range(16):
 old=next(csv.DictReader((A/('ramulator_N%02d.csv'%rank)).open()));new=next(csv.DictReader((R/('ramulator_N%02d.csv'%rank)).open()))
 assert old['bytes']==new['bytes']=='4096' and int(new['service_cycles'])==math.ceil(int(old['service_cycles'])*1.25)
out=dict(state='PASS_LIMITED_16_NODE_CLOCK_BINDING_CORRECTED',CPU_clock_rate=2.5,DRAM_cycle_scale=1.25,CPU_ready_quantization='ceil1ns',clock_observations_each_round=11296,all_domain_ready_bounds_verified=True,full_steps_1_7=False,remaining='full opcode/CPU software/SRAM Bank costs and complete distributed layer still separate')
(R/'CLOCK_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
