#!/usr/bin/env python3
"""Resumable HiBand+Sem-MoE continuous-microbatch scale suite."""
import argparse,json,subprocess,sys,time
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--deepstack-python',type=Path,required=True);ap.add_argument('--deepstack-root',type=Path,required=True);ap.add_argument('--config',type=Path,required=True);ap.add_argument('--compute-profile',type=Path,required=True);ap.add_argument('--context',type=int,default=128);ap.add_argument('--scales',type=int,nargs='+',default=[4,8,16]);ap.add_argument('--steps',type=int,default=2);ap.add_argument('--partition-capacity-mib',type=int,default=512);ap.add_argument('--tag',default='deepstack_v1');a=ap.parse_args()
    root=a.root;out=root/'results'/f'combo_scale_ctx{a.context}_{a.tag}';out.mkdir(parents=True,exist_ok=True);status_path=out/'status.json'
    state=json.loads(status_path.read_text()) if status_path.exists() else {'status':'RUNNING','scope':'diagnostic scale matrix; no formal SOTA claim','cases':{}}
    def save():status_path.write_text(json.dumps(state,indent=2)+'\n')
    state['status']='RUNNING';save()
    placement=root/'results'/f'sem_moe_reproduction_ctx{a.context}_v2'/'placement.json'
    try:
        for c in a.scales:
            key=f'c{c}';case=out/key;graph=case/'graph';run=case/'run';timing=case/'deepstack_op_timing.csv';attr=case/'critical_path_attribution_v2.json'
            if state['cases'].get(key,{}).get('status')=='PASS':continue
            case.mkdir(parents=True,exist_ok=True);state['cases'][key]={'status':'BUILDING_GRAPH','updated_unix':time.time()};save()
            subprocess.run([sys.executable,str(root/'build_paging_smoke.py'),'--root',str(root),'--context',str(a.context),'--batch',str(c),'--steps',str(a.steps),'--microbatch-size','1','--partition-capacity-mib',str(a.partition_capacity_mib),'--placement',str(placement),'--compute-profile',str(a.compute_profile),'--hiband','--out',str(graph)],check=True)
            state['cases'][key].update(status='BUILDING_DEEPSTACK_TIMING',updated_unix=time.time());save()
            subprocess.run([str(a.deepstack_python),str(root/'build_deepstack_op_timing_v3.py'),'--deepstack-root',str(a.deepstack_root),'--ops',str(graph/'ops.csv'),'--config',str(a.config),'--output',str(timing)],check=True)
            state['cases'][key].update(status='RUNNING_LEGOSIM',updated_unix=time.time());save()
            subprocess.run([sys.executable,str(root/'run_paging_smoke.py'),'--root',str(root),'--graph',str(graph),'--out',str(run),'--hiband','--deepstack-timing',str(timing)],check=True)
            state['cases'][key].update(status='ATTRIBUTING',updated_unix=time.time());save()
            subprocess.run([sys.executable,str(root/'critical_path_attribution_v2.py'),'--graph',str(graph),'--run',str(run),'--out',str(attr)],check=True)
            validation=json.loads((run/'validation.json').read_text());attribution=json.loads(attr.read_text());meta=json.loads((graph/'graph_manifest.json').read_text())
            state['cases'][key]={'status':'PASS','updated_unix':time.time(),'validation':validation,'components':attribution['components'],'conservation_error_cycles':attribution['conservation_error_cycles'],'graph':{k:meta[k] for k in ('operations','hits','misses','microbatch_size','microbatches')}};save()
        state['status']='PASS';save()
    except BaseException as exc:state['status']='FAILED';state['error']=repr(exc);save();raise
if __name__=='__main__':main()
