import os
os.environ['OMP_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
import pathlib,json,time,hashlib,signal,numpy as np,torch
R=pathlib.Path(__file__).resolve().parent;P=R.parent/'lingbot_step4_bitexact_20261029_v4';torch.set_num_threads(1);golds={b:torch.load(P/'external_attention_attempt1'/(b+'_core.pt'),weights_only=True)[0] for b in ['cond','uncond']};seen={};end=time.monotonic()+140000
while time.monotonic()<end:
 terminal=None
 if (R/'STATUS.json').exists():
  try:terminal=json.loads((R/'STATUS.json').read_text())['state']
  except json.JSONDecodeError:pass
 for case in sorted(R.glob('case*')):
  if not case.is_dir():continue
  for rank in range(16):
   D=case/('N%02d'%rank)
   if not (D/'PROGRESS.json').exists():continue
   try:progress=json.loads((D/'PROGRESS.json').read_text())
   except (json.JSONDecodeError,OSError):continue
   for branch,S in [('cond',49883),('uncond',48986)]:
    limit=S if (D/(branch+'_PASS.json')).exists() or (branch=='cond' and progress['branch']=='uncond') else (progress['verified_query_end'] if progress['branch']==branch else 0)
    key=case.name+'_'+branch+'_N%02d'%rank;start=seen.get(key,0)
    if limit<=start:continue
    q=D/(branch+'_core.npy')
    if not q.exists():continue
    a=np.load(q,mmap_mode='r');ref=golds[branch][start:limit,rank].float().numpy();bad=int(np.count_nonzero(a[start:limit].view(np.uint32)!=ref.view(np.uint32)))
    if bad:
     fail=R/'LIVE_CORE_FAILURE';fail.mkdir(exist_ok=False);np.save(fail/'actual.npy',a[start:limit]);np.save(fail/'reference.npy',ref);report=dict(case=case.name,branch=branch,rank=rank,begin=start,end=limit,bit_mismatches=bad);(fail/'FAILURE.json').write_text(json.dumps(report,indent=2));(R/'STOP_REASON.json').write_text(json.dumps(dict(reason='LIVE_INDEPENDENT_GPU_CORE_FIRST_DIFFERENCE',detail=report),indent=2));pid=json.loads((R/'LAUNCH.json').read_text())['pid'];cmd=pathlib.Path('/proc/'+str(pid)+'/cmdline').read_bytes();assert str(R/'config.yml').encode() in cmd and b'interchiplet' in cmd;os.killpg(pid,signal.SIGTERM);raise RuntimeError(str(report))
    seen[key]=limit
 (R/'LIVE_CORE_AUDIT_PROGRESS.json').write_text(json.dumps(dict(state='RUNNING_INDEPENDENT_GPU_CORE_PREFIX',checked_query_rows_by_head=seen,checked_BF16_elements=sum(seen.values())*128,bit_mismatches=0,whole_step5=False),indent=2))
 if terminal and terminal.startswith(('PASS','STOPPED')):
  if terminal.startswith('PASS'):assert len(seen)==64 and sum(seen.values())==2*98869*16
  (R/'LIVE_CORE_AUDIT_FINAL.json').write_text(json.dumps(dict(state='PASS_FULL_CORE_TWO_ROUNDS' if terminal.startswith('PASS') else 'STOPPED_PRODUCTION_SCOPE_RETAINED',checked_rows_by_head=seen,bit_mismatches=0),indent=2));break
 time.sleep(10)
else:raise TimeoutError('live core observer bounded wait expired')
