#!/usr/bin/env python3
"""Bank-oracle-only screening; results are not end-to-end claims."""
import argparse,csv,json,subprocess,sys,time
from pathlib import Path

def timing_sum(path):
    out={'actual_cycles_npu':0,'ideal_balanced_cycles_npu':0,'bank_mapping_row_penalty_cycles_npu':0}
    with path.open(newline='') as f:
        for r in csv.DictReader(f):
            for k in out:out[k]+=int(r[k])
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--deepstack-python',type=Path,required=True);ap.add_argument('--deepstack-root',type=Path,required=True);a=ap.parse_args()
    root=a.root;dest=root/'results/bank_bottleneck_screen_v1';dest.mkdir(parents=True,exist_ok=True);status=dest/'status.json';state={'status':'RUNNING','scope':'Bank-oracle screening only; not end-to-end evidence','cases':[]};status.write_text(json.dumps(state,indent=2)+'\n')
    try:
      for context in (128,512):
       for scale in (1,8,16):
        for policy in ('exploratory_low_skew','exploratory_high_skew'):
         name=f'ctx{context}_c{scale}_{policy}';case=dest/name;graph=case/'graph';case.mkdir(parents=True,exist_ok=True)
         subprocess.run([sys.executable,str(root/'build_paging_smoke.py'),'--root',str(root),'--context',str(context),'--batch',str(scale),'--steps','2','--microbatch-size','1','--cohort-policy',policy,'--cohort-repeat','1','--placement',str(root/f'results/sem_moe_reproduction_ctx{context}_v2/placement.json'),'--compute-profile',str(root/'scalesim_compute_profile_v1.json'),'--hiband','--out',str(graph)],check=True)
         sums={}
         for mapping,cfg in [('normal',root/'deepstack_bank_oracle_v3_6.json'),('balanced_xor',root/'deepstack_bank_oracle_v3_6_balanced_xor.json')]:
          timing=case/f'{mapping}_timing.csv';subprocess.run([str(a.deepstack_python),str(root/'build_deepstack_op_timing_v3.py'),'--deepstack-root',str(a.deepstack_root),'--ops',str(graph/'ops.csv'),'--config',str(cfg),'--output',str(timing)],check=True);sums[mapping]=timing_sum(timing)
         n,b=sums['normal'],sums['balanced_xor'];meta=json.loads((graph/'graph_manifest.json').read_text());row={'name':name,'context':context,'scale':scale,'policy':policy,'misses':meta['misses'],'normal':n,'balanced_xor':b,'actual_reduction_cycles':n['actual_cycles_npu']-b['actual_cycles_npu'],'actual_reduction_fraction':(n['actual_cycles_npu']-b['actual_cycles_npu'])/n['actual_cycles_npu'] if n['actual_cycles_npu'] else 0,'updated_unix':time.time()};state['cases'].append(row);status.write_text(json.dumps(state,indent=2)+'\n')
      state['status']='PASS';status.write_text(json.dumps(state,indent=2)+'\n')
    except BaseException as e:state['status']='FAILED';state['error']=repr(e);status.write_text(json.dumps(state,indent=2)+'\n');raise
if __name__=='__main__':main()
