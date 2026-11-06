# Python2, installed Sniper statistics reader; read-only with respect to run.
import sys,os,json,re
sys.path.insert(0,'/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim/tools')
import sniper_lib
root=os.path.dirname(os.path.abspath(__file__))
d=sniper_lib.get_results(resultsdir=os.path.join(root,'sniper'));r=d['results'];c=d['config']
keep={k:v for k,v in r.items() if k in ['global.time','corefreq','fs_to_cycles_cores','performance_model.elapsed_time','performance_model.nonidle_elapsed_time','performance_model.instruction_count']}
log=open(os.path.join(root,'run1','proc_r2_p1_t0','cpu.log')).read();cycles=[int(v) for v in re.findall(r'\[INTERCMD\] CYCLE (\d+)',log) if int(v)]
out=dict(stats=keep,configured_core_GHz=c['perf_model/core/frequency'],reported_nonzero_native_cycles=cycles,scope='raw statistics and interface ticks; no unvalidated total-time equivalence asserted')
with open(os.path.join(root,'SNIPER_CLOCK_STATISTICS.json'),'w') as f:json.dump(out,f,indent=2)
print(json.dumps(out,indent=2))
