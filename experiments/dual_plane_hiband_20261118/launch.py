"""Four independent single-threaded jobs; bounded cluster concurrency."""
import concurrent.futures, hashlib, json, os, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def run(task):
    case,arm,setup,eta,eps,bank=task
    name=f'{case}_{arm}_s{setup}_e{eta}_b{bank}'
    out=ROOT/'results'/f'{name}.json';err=out.with_suffix('.err')
    cmd=[str(ROOT/'model'),str(ROOT/'cases'/f'{case}.txt'),arm,str(setup),str(eta),str(eps),str(bank)]
    with out.open('w') as stdout,err.open('w') as stderr:
        done=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=1200,env={**os.environ,'OMP_NUM_THREADS':'1'})
    if done.returncode:return name,'FAIL '+err.read_text()[:300]
    d=json.loads(out.read_text());assert d['status']=='PASS_DELIVERY_AND_DRAIN'
    return name,'PASS '+str(d['wall_ms'])+'ms'
def main():
    (ROOT/'results').mkdir(exist_ok=True)
    cases=json.loads((ROOT/'CASES.json').read_text())
    arms=['mesh','dual','proposed','delay_control','hiband_FG','hiband_GB','hiband_LB','gets_only','moe_only']
    tasks=[(c['name'],a,40,0,32,8) for c in cases for a in arms]
    # Runtime-installation and memory service sensitivity on the 16-token,
    # independent seed, distributed case. Not added as untested performance.
    ref='fit16_641103_distributed'
    tasks += [(ref,'proposed',s,0,32,8) for s in [0,160,640]]
    tasks += [(ref,'delay_control',s,0,32,8) for s in [0,160,640]]
    tasks += [(ref,a,40,0,32,32) for a in ['dual','proposed','hiband_FG','hiband_GB','hiband_LB']]
    (ROOT/'RUN_MANIFEST.json').write_text(json.dumps(dict(start_unix=time.time(),workers=4,tasks=tasks,
       model_sha256=hashlib.sha256((ROOT/'model.cpp').read_bytes()).hexdigest(),
       executable_sha256=hashlib.sha256((ROOT/'model').read_bytes()).hexdigest(),
       cases_manifest_sha256=hashlib.sha256((ROOT/'CASES.json').read_bytes()).hexdigest(),
       runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2))
    failures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for name,status in pool.map(run,tasks):
            print(name,status,flush=True)
            if status.startswith('FAIL'):failures.append(name)
    (ROOT/'RUN_STATUS.json').write_text(json.dumps(dict(finished_unix=time.time(),jobs=len(tasks),failures=failures)))
    if failures:raise SystemExit(1)
if __name__=='__main__': main()
