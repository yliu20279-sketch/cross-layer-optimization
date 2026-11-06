"""Require application receipts before accepting simulator process exit codes."""
import json,os,sys,hashlib
from pathlib import Path
def verify(root):
 r=Path(root);d=r/'case1'
 assert json.loads((r/'cpu_data/CPU_PASS.json').read_text())['state']=='PASS_LAYER1_PREFILL_DECODE'
 files=json.loads((d/'FILES.json').read_text());checks=json.loads((d/'CHECKS.json').read_text())
 strict=[v for v in checks if v['strict']]
 assert len(files)==56 and len(strict)==12 and all(v['exact'] and v['different']==0 for v in strict)
 for v in files:assert hashlib.sha256((d/v['path']).read_bytes()).hexdigest()==v['sha256']
 for phase in ['prefill','decode']:
  item=next(v for v in files if v['phase']==phase and v['layer']==1 and v['stage']=='output')
  assert (r/'cpu_data'/(phase+'_ACTUAL.bin')).read_bytes()==(d/item['path']).read_bytes()
 return dict(state='PASS_APPLICATION_RECEIPT_GATE',strict_checks=12,CPU_outputs=2,stage_files=56)
if __name__=='__main__':
 try:result=verify(sys.argv[1])
 except (OSError,AssertionError,ValueError,StopIteration) as e:
  print('REJECT_APPLICATION_RECEIPT',type(e).__name__,str(e),flush=True);sys.exit(8)
 print(json.dumps(result),flush=True)
 if len(sys.argv)>2:os.execv(sys.argv[2],sys.argv[2:])
