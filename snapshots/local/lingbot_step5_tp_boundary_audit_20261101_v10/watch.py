import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import pathlib,json,time,signal,traceback,numpy as np,torch
A=pathlib.Path(__file__).resolve().parent;R=A.parent/'lingbot_step5_full_tp_20261101_v6';G=A.parent/'lingbot_step3_capture_20261028_v1'
os.umask(0o022);torch.set_num_threads(1);torch.set_num_interop_threads(1)
def put(n,v):
 q=A/(n+'.tmp');q.write_text(json.dumps(v,indent=2));q.replace(A/n)
try:
 gold={(b,n):torch.load(G/'fixtures'/('full_on_s00_'+b+'_L00_'+n+'.pt'),weights_only=True)[0] for b in ['cond','uncond'] for n in ['attention_output','ffn_input']}
 seen={};end=time.monotonic()+92000;total=0
 while time.monotonic()<end:
  terminal=None
  if (R/'STATUS.json').exists():
   try:terminal=json.loads((R/'STATUS.json').read_text())['state']
   except json.JSONDecodeError:pass
  for case in sorted(R.glob('case*')):
   if not case.is_dir():continue
   for rank in range(16):
    D=case/('N%02d'%rank)
    try:p=json.loads((D/'PROGRESS.json').read_text())
    except (OSError,json.JSONDecodeError):continue
    for branch,S in [('cond',49883),('uncond',48986)]:
     limit=S if (D/(branch+'_PASS.json')).exists() or (branch=='cond' and p['branch']=='uncond') else (p['verified_query_end'] if p['branch']==branch else 0)
     count=len(range(rank,limit,16));key=case.name+'_'+branch+'_N%02d'%rank;start=seen.get(key,0)
     if count<=start:continue
     idx=rank+16*np.arange(start,count)
     for name in ['attention_output','ffn_input']:
      a=np.load(D/(branch+'_'+name+'.npy'),mmap_mode='r')[start:count];ref=gold[branch,name][idx].float().numpy()
      bad=np.flatnonzero(a.view(np.uint32).ravel()!=ref.view(np.uint32).ravel())
      if len(bad):
       F=A/'FIRST_DIFFERENCE';F.mkdir(exist_ok=False);np.save(F/'actual.npy',a);np.save(F/'reference.npy',ref)
       detail=dict(case=case.name,branch=branch,rank=rank,stage=name,origin_begin=start,origin_end=count,bit_mismatches=len(bad),first_flat=int(bad[0]))
       put('FIRST_DIFFERENCE/FAILURE.json',detail)
       pid=json.loads((R/'LAUNCH.json').read_text())['pid'];cmd=pathlib.Path('/proc/'+str(pid)+'/cmdline').read_bytes()
       assert str(R/'config.yml').encode() in cmd and b'interchiplet' in cmd
       put('STOP_ACTION.json',dict(reason='independent boundary first difference',pid=pid,detail=detail));os.killpg(pid,signal.SIGTERM)
       raise RuntimeError(str(detail))
      total+=a.size
     seen[key]=count
  put('PROGRESS.json',dict(state='RUNNING_INDEPENDENT_O_AND_FFN_BOUNDARIES',origin_rows_by_rank=seen,checked_BF16_elements=total,bit_mismatches=0,target_GPU_count=0,whole_step5=False))
  if terminal and terminal.startswith(('PASS','STOPPED')):
   if terminal.startswith('PASS'):assert len(seen)==64 and sum(seen.values())==2*98869
   put('FINAL.json',dict(state='PASS_TWO_ROUND_BOUNDARIES' if terminal.startswith('PASS') else 'STOPPED_PRODUCTION_PRESERVED',origin_rows_by_rank=seen,checked_BF16_elements=total,bit_mismatches=0,whole_step5=False));break
  time.sleep(10)
 else:raise TimeoutError('bounded observer expired')
except BaseException:
 put('FAILURE.json',dict(error=traceback.format_exc()));raise
