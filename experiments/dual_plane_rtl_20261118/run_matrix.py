"""Bounded RTL workers; source, input, binary and result hashes are bound."""
import argparse,concurrent.futures,hashlib,json,os,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,default=8);args=ap.parse_args();assert 1<=args.workers<=8
    build=json.loads((R/'CURRENT_BUILD.json').read_text());assert build['status']=='PASS'
    root=Path(build['path']);image=build['image'];cases=json.loads((R/'CASES.json').read_text())
    out=R/('pilot' if args.pilot else 'results')/build.get('build_id',build['source_digest']);out.mkdir(parents=True,exist_ok=True)
    arms=[('mesh',0,0),('dual',1,0),('runtime',1,0),('forced_cs',1,0),
          ('hiband_FG',2,0),('hiband_GB',2,1),('hiband_LB',2,2),('gets_only',0,0),('moe_only',0,0)]
    tasks=[dict(case=c['name'],arm=arm,mode=mode,hiband=hb,bank=8,clock=1) for c in cases for arm,mode,hb in arms]
    tasks += [dict(case='fit16_641103_distributed',arm=a,mode=m,hiband=hb,bank=b,clock=1) for b in [0,32] for a,m,hb in arms if a in ['dual','runtime','hiband_FG','hiband_GB','hiband_LB']]
    tasks += [dict(case='fit16_641103_distributed',arm='runtime',mode=1,hiband=0,bank=8,clock=c) for c in [5,10]]
    if args.pilot:tasks=[t for t in tasks if t['case']=='fit4_161101_distributed' and t['bank']==8 and t['clock']==1]
    manifest=dict(status='running',rtl_digest=build['source_digest'],image=image,workers=args.workers,tasks=tasks,
       binaries={str(m):hashlib.sha256((root/f'obj{m}/Vdut').read_bytes()).hexdigest() for m in [0,1,2]},
       case_hashes={c['name']:c['case_sha256'] for c in cases},start_unix=time.time(),result_path=str(out))
    def save():(R/('PILOT.json' if args.pilot else 'MATRIX.json')).write_text(json.dumps(manifest,indent=2));(out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2))
    save()
    def run(task):
        name=task['case']+'_'+task['arm']+'_b'+str(task['bank'])+(('_clk'+str(task['clock'])) if task['clock']!=1 else '')
        case=R/'cases'/(task['case']+'.txt')
        assert hashlib.sha256(case.read_bytes()).hexdigest()==manifest['case_hashes'][task['case']]
        cmd=['docker','run','--rm','--network','none','--cpus','1','--memory','3g','--pids-limit','256',
          '--mount',f'type=bind,src={root},dst=/rtl,readonly','--mount',f'type=bind,src={R/"cases"},dst=/cases,readonly',image,
          f'/rtl/obj{task["mode"]}/Vdut','--case','/cases/'+case.name,task['arm'],'--bank',str(task['bank']),'--clock-ns',str(task['clock'])]
        if task['mode']!=1:cmd+=['--shared']
        if task['mode']==2:cmd+=['--mode',str(task['hiband'])]
        start=time.time()
        with (out/(name+'.json')).open('w') as stdout,(out/(name+'.err')).open('w') as stderr:
            p=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=900)
        if p.returncode:return dict(name=name,status='FAIL',returncode=p.returncode,error=(out/(name+'.err')).read_text()[-1000:])
        d=json.loads((out/(name+'.json')).read_text());assert d['status']=='PASS_RTL_DELIVERY_PAYLOAD_AND_SRAM'
        return dict(name=name,status='PASS',seconds=time.time()-start)
    runs=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(run,t):t for t in tasks}
        for f in concurrent.futures.as_completed(futures):
            try:r=f.result()
            except Exception as e:r=dict(task=futures[f],status='FAIL',error=repr(e))
            runs.append(r);manifest['runs']=runs;manifest['completed']=len(runs);save();print(r,flush=True)
    manifest.update(status='PASS' if all(x['status']=='PASS' for x in runs) else 'FAILED',runs=runs,finished_unix=time.time());save()
    if manifest['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
