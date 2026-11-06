"""Bounded sequential real-route diagnostic screen; fail closed, no GPU."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root
    out=root/'results/diagnostic_screen_v1';out.mkdir(exist_ok=True)
    state={'status':'RUNNING','scope':'baseline EP16 diagnostics only, not formal four-control matrix','cases':[]}
    def save():(out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
    save();os.environ.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    try:
        for context,batch in ((128,1),(512,16)):
            case=out/f'ctx{context}_c{batch}_s2';graph=case/'graph';run=case/'run'
            if (run/'validation.json').exists():
                result=json.loads((run/'validation.json').read_text());assert result['status']=='PASS'
            else:
                subprocess.run([sys.executable,str(root/'build_paging_smoke.py'),'--root',str(root),'--context',str(context),'--batch',str(batch),'--steps','2','--out',str(graph)],check=True)
                subprocess.run([sys.executable,str(root/'run_paging_smoke.py'),'--root',str(root),'--graph',str(graph),'--out',str(run)],check=True)
                result=json.loads((run/'validation.json').read_text());assert result['status']=='PASS'
            state['cases'].append(dict(context=context,batch=batch,validation=result));save()
        state['status']='PASS';save()
    except BaseException as exc:
        state.update(status='FAILED',error=repr(exc));save();raise
if __name__=='__main__':main()
