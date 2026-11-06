"""Four-control diagnostic smoke, sequential and fail-closed."""
import argparse,json,os,subprocess,sys
from pathlib import Path
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--context',type=int,default=128);ap.add_argument('--batch',type=int,default=1);ap.add_argument('--steps',type=int,default=2);ap.add_argument('--microbatch-size',type=int,default=0);ap.add_argument('--compute-profile',type=Path);ap.add_argument('--deepstack-baseline-timing',type=Path);ap.add_argument('--deepstack-sem-timing',type=Path);ap.add_argument('--tag',default='v1');a=ap.parse_args()
    root=a.root;dest=root/'results'/f'four_control_smoke_ctx{a.context}_c{a.batch}_{a.tag}';dest.mkdir(exist_ok=True)
    placement=root/'results'/f'sem_moe_reproduction_ctx{a.context}_v2'/'placement.json';assert placement.exists()
    state={'status':'RUNNING','scope':'diagnostic only; no formal SOTA claim','cases':[]};save=lambda:(dest/'status.json').write_text(json.dumps(state,indent=2)+'\n');save()
    try:
        for name,sem,hiband in [('baseline_ep',0,0),('hiband',0,1),('sem_moe',1,0),('hiband_sem_moe',1,1)]:
            case=dest/name;graph=case/'graph';run=case/'run'
            build=[sys.executable,str(root/'build_paging_smoke.py'),'--root',str(root),'--context',str(a.context),'--batch',str(a.batch),'--steps',str(a.steps),'--out',str(graph)]
            if a.microbatch_size:build+=['--microbatch-size',str(a.microbatch_size)]
            if a.compute_profile:build+=['--compute-profile',str(a.compute_profile)]
            if sem:build+=['--placement',str(placement)]
            if hiband:build+=['--hiband']
            subprocess.run(build,check=True)
            launch=[sys.executable,str(root/'run_paging_smoke.py'),'--root',str(root),'--graph',str(graph),'--out',str(run)]
            if hiband:launch+=['--hiband']
            timing=a.deepstack_sem_timing if sem else a.deepstack_baseline_timing
            if timing:launch+=['--deepstack-timing',str(timing)]
            subprocess.run(launch,check=True)
            validation=json.loads((run/'validation.json').read_text());manifest=json.loads((run/'run_manifest.json').read_text());graphmeta=json.loads((graph/'graph_manifest.json').read_text())
            state['cases'].append({'scheme':name,'validation':validation,'graph':{k:graphmeta[k] for k in ('operations','hits','misses','scheme','compute_timing','microbatch_size')},'fixed_mode':not hiband});save()
        state['status']='PASS';save()
    except BaseException as exc:state.update(status='FAILED',error=repr(exc));save();raise
if __name__=='__main__':main()
