# Python2: original Sniper statistics reader.
import sys,os,json
sys.path.insert(0,'/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim/tools')
import sniper_lib
R=os.path.dirname(os.path.abspath(__file__))
d=sniper_lib.get_results(resultsdir=os.path.join(R,'roi_attempt1','sim'));r=d['results'];c=d['config']
keys=['performance_model.elapsed_time','performance_model.nonidle_elapsed_time','performance_model.idle_elapsed_time','performance_model.instruction_count','performance_model.cycle_count','corefreq']
result=dict(stats={k:r[k] for k in keys},config={k:c[k] for k in ['general/total_cores','perf_model/core/frequency','perf_model/l1_icache/cache_size','perf_model/l1_dcache/cache_size','perf_model/l2_cache/cache_size','perf_model/l3_cache/cache_size','perf_model/dram/type','perf_model/dram/per_controller_bandwidth','perf_model/dram/latency']},
 scope='CPU software fallback profile only; no modeled data transfers or NPU exp/TopK ISA')
with open(os.path.join(R,'roi_attempt1','METRICS.json'),'w') as f:json.dump(result,f,indent=2)
print(json.dumps(result,indent=2))
