# Python2: use the installed Sniper's own statistics reader.
import sys,os,json
sys.path.insert(0,'/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim/tools')
import sniper_lib
root=os.path.dirname(os.path.abspath(__file__))
rows=[]
for mode in ['decode','encode']:
 d=sniper_lib.get_results(resultsdir=os.path.join(root,'attempt1',mode+'_sim'))
 r=d['results'];c=d['config']
 keep={k:v for k,v in r.items() if k.startswith('performance_model.') or k in ['global.time','corefreq','fs_to_cycles_cores']}
 cfg={k:v for k,v in c.items() if k in ['general/total_cores','perf_model/core/frequency','perf_model/core/type','perf_model/l1_icache/cache_size','perf_model/l1_dcache/cache_size','perf_model/l2_cache/cache_size','perf_model/l3_cache/cache_size','perf_model/dram/type','perf_model/dram/latency','perf_model/dram/per_controller_bandwidth']}
 rows.append(dict(mode=mode,stats=keep,resolved_config=cfg))
with open(os.path.join(root,'attempt1','SNIPER_RAW_METRICS.json'),'w') as f:json.dump(rows,f,indent=2)
print(json.dumps(rows,indent=2))
