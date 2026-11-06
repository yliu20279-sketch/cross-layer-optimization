import json,time,tarfile,hashlib,traceback
from pathlib import Path
R=Path(__file__).resolve().parent;deadline=time.monotonic()+45200
try:
 while not (R/'DELIVERY_STATUS.json').exists() or not (R/'RAW_ORACLE_AUDIT.json').exists():
  if (R/'COLLECTOR_FAILURE.txt').exists() or (R/'RAW_ORACLE_FAILURE.txt').exists():raise RuntimeError('primary or strict FP32 audit failed; no promotion')
  if time.monotonic()>deadline:raise TimeoutError('independent safe archive deadline')
  time.sleep(10)
 assert json.loads((R/'DELIVERY_STATUS.json').read_text())['state']=='PASS_LIMITED_FULL_TWO_LAYER_CPU_FP32_SRAM_REVIEW'
 assert json.loads((R/'RAW_ORACLE_AUDIT.json').read_text())['state']=='PASS_LIMITED_759_FP32_MATRICES_AND_56_STAGES_TWO_ROUND'
 members={p for p in R.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name not in ['EXP16_ALL_FP32.bin','SAFE_MANIFEST.json','SAFE_DELIVERY_STATUS.json','safe_collect.log'] and (p.stat().st_size<40*2**20 or p.suffix in ['.csv','.json','.bin','.txt','.log'])}
 # Reused CPU oracle is a symlink directory; include its relevant payloads explicitly.
 members.update(p for p in (R/'oracle_cpu').iterdir() if p.is_file() and p.suffix in ['.json','.bin'])
 def sha(p):
  h=hashlib.sha256()
  with p.open('rb') as f:
   while b:=f.read(8*2**20):h.update(b)
  return h.hexdigest()
 manifest=[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(members)];(R/'SAFE_MANIFEST.json').write_text(json.dumps(manifest,indent=2));pack=R.parent/(R.name+'_SAFE_REVIEW.tar.gz')
 with tarfile.open(pack,'w:gz',dereference=True) as t:
  for p in sorted(members)+[R/'SAFE_MANIFEST.json']:t.add(p,arcname=R.name+'/'+str(p.relative_to(R)))
 out=dict(state='PASS_LIMITED_FULL_FUNCTIONAL_CPU_FP32_SRAM_SAFE_REVIEW',members=len(members),archive=str(pack),bytes=pack.stat().st_size,sha256=sha(pack),scope='all numerical/clock CSV evidence retained, symlinks materialized; full16GiB exp instruction table remains on113 with complete SHA/provenance',full_steps_1_7=False)
 (R/'SAFE_DELIVERY_STATUS.json').write_text(json.dumps(out,indent=2));print(json.dumps(out),flush=True)
except Exception:
 (R/'SAFE_COLLECTOR_FAILURE.txt').write_text(traceback.format_exc());raise
