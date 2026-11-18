"""Extend fixed L2 to 30 cases: reuse 24, execute only 96 missing runs."""
import concurrent.futures,hashlib,json,subprocess,time,traceback
from pathlib import Path
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):
 t=p.with_suffix('.tmp');t.write_text(json.dumps(d,indent=2)+'\n');t.replace(p)
def main():
 s=json.loads((R/'SOURCE_MANIFEST.json').read_text());start=json.loads((R/'EXTENSION_START.json').read_text());parent=Path(start['precheck_path'])
 m=json.loads((R/'MATRIX.json').read_text());assert m['status']=='ready' and len(m['runs'])==24 and len(m['tasks'])==120
 b=json.loads((parent/'BUILD.json').read_text());assert b['status']=='PASS'
 for t in b['targets']:assert sha(parent/f'obj{t["mode"]}/Vdut')==t['binary_sha256']
 for n,h in s['source_sha256'].items():assert sha(parent/n)==h
 tasks=start['new_tasks'];assert len(tasks)==96
 m['status']='running';write(R/'MATRIX.json',m)
 def run(t):
  name=t['case']+'_'+t['arm']+'_type_priority_b8';p=R/'results'/(name+'.json')
  assert not p.exists(),'Never rerun an existing result'
  assert sha(R/'cases'/(t['case']+'.txt'))==m['case_hashes'][t['case']]
  cmd=['docker','run','--rm','--network','none','--cpus','1','--memory','3g','--pids-limit','256','--mount',f'type=bind,src={parent},dst=/rtl,readonly','--mount',f'type=bind,src={R/"cases"},dst=/cases,readonly',s['image'],f'/rtl/obj{t["mode"]}/Vdut','--case','/cases/'+t['case']+'.txt',t['arm'],'--bank','8','--clock-ns','1','--shared']
  if t['mode']==2:cmd+=['--mode',str(t['hiband'])]
  begin=time.time()
  with p.open('x') as out,(R/'results'/(name+'.err')).open('x') as err:ret=subprocess.run(cmd,stdout=out,stderr=err,timeout=900)
  if ret.returncode:return dict(name=name,task=t,status='FAIL',returncode=ret.returncode,command=cmd)
  assert json.loads(p.read_text())['status']=='PASS_RTL_DELIVERY_PAYLOAD_AND_SRAM'
  return dict(name=name,task=t,status='PASS',command=cmd,sha256=sha(p),seconds=time.time()-begin)
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
  futures={pool.submit(run,t):t for t in tasks}
  for f in concurrent.futures.as_completed(futures):
   try:r=f.result()
   except BaseException as e:r=dict(task=futures[f],status='FAIL',error=repr(e))
   m['runs'].append(r);m['completed']=len(m['runs']);m['new_completed']=len(m['runs'])-24;write(R/'MATRIX.json',m);print(json.dumps(r),flush=True)
 m.update(status='PASS' if all(x['status']=='PASS' for x in m['runs']) else 'FAILED',finished=time.time());write(R/'MATRIX.json',m)
 assert m['status']=='PASS','Retain failures without retry'
 subprocess.run(['python3',str(R/'audit_full.py')],cwd=R,check=True)
if __name__=='__main__':
 try:main()
 except BaseException as e:
  write(R/'FAILURE.json',dict(status='FAILED_RETAINED_NO_RETRY',error=repr(e),traceback=traceback.format_exc(),time=time.time()));raise
