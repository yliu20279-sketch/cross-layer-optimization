"""Minimize dynamic HiBand liveness failure by changing only NET scope labels."""
import argparse,csv,json,os,shutil,subprocess,sys
from pathlib import Path
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    state={'status':'RUNNING','source':str(a.source),'cases':[]}
    for label,scope in [('all_global','global'),('all_local','local')]:
        case=a.out/label;graph=case/'graph';run=case/'run';shutil.copytree(a.source,graph,dirs_exist_ok=True)
        with (graph/'ops.csv').open(newline='') as f:rows=list(csv.DictReader(f));fields=rows[0].keys()
        for r in rows:
            if r['kind']=='NET':r['scope']=scope
        with (graph/'ops.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
        env=os.environ.copy();env['HB_PROGRESS_WATCHDOG_CYCLES']='1000000'
        p=subprocess.run([sys.executable,str(a.root/'run_paging_smoke.py'),'--root',str(a.root),'--graph',str(graph),'--out',str(run),'--hiband'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        state['cases'].append({'case':label,'returncode':p.returncode,'validation_exists':(run/'validation.json').exists(),'stdout_tail':p.stdout[-1000:]});(a.out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
    state['status']='PASS_DIAGNOSTIC_COMPLETED';(a.out/'status.json').write_text(json.dumps(state,indent=2)+'\n');print(json.dumps(state,indent=2))
if __name__=='__main__':main()
