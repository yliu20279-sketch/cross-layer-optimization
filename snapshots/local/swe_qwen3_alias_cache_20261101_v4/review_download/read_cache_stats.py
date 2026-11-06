import sys,json,os
sys.path.insert(0,'/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim/tools')
import sniper_lib
R=os.path.dirname(os.path.abspath(__file__))
rows=[]
for a,b in [(100,110),(120,130),(130,140),(101,111),(121,131),(131,141)]:
 r=sniper_lib.get_results(resultsdir=os.path.join(R,'cache_probe_run_v4'),partial=('marker-%d-0'%a,'marker-%d-0'%b))['results'];keys=['L1-D.loads','L1-D.load-misses','L2.loads','L2.load-misses','L3.loads','L3.load-misses','L1-D.evict-M','L2.evict-M','L3.evict-M','L3.coherency-writebacks','performance_model.elapsed_time','performance_model.nonidle_elapsed_time'];vals={k:(r[k][0] if isinstance(r[k],list) else r[k]) for k in keys if k in r};rows.append(dict(begin=a,end=b,metrics=vals))
print(json.dumps(rows,indent=2));open(os.path.join(R,'CACHE_MARKER_STATS.json'),'w').write(json.dumps(rows,indent=2))
