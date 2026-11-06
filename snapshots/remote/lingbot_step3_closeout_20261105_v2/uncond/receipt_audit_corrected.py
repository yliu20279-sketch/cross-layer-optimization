import json,csv,re,hashlib,tarfile
from pathlib import Path
from fractions import Fraction
from math import ceil
from completion_gate import CompletionGate, KINDS
R=Path(__file__).resolve().parent
result=json.loads((R/'INDEPENDENT_AUDIT.json').read_text())
assert result['state'].startswith('PASS_LIMITED')
reports=[]
for k,branch in [(1, 'uncond'), (2, 'uncond')]:
 paths=list((R/'run').glob(f'proc_r{k}_p1_t*'))
 cpu=next(p/'cpu.log' for p in paths if (p/'cpu.log').exists())
 dma=next(p/'dma_receipts.csv' for p in paths if (p/'dma_receipts.csv').exists())
 matches=re.findall(r'MAINT_DRAIN (\d+) (\d+) (\d+) (\d+)',cpu.read_text())
 assert len(matches)==1
 issued,pending,now_fs,done_fs=map(int,matches[0])
 assert issued>0 and pending==0 and done_fs>now_fs
 g=json.loads((R/f'case{k}/N00/GATE.json').read_text())
 rows=list(csv.reader(dma.open()))
 assert len(rows)==2
 transfers=[]
 for row in rows:
  tx,direction,n,segments,start,done=row
  n,segments,start,done=map(int,(n,segments,start,done))
  service=sum(ceil(Fraction(min(256,n-offset)*100,5504)) for offset in range(0,n,256))
  assert segments==ceil(n/256) and done==start+270+service
  transfers.append(dict(direction=direction,bytes=n,segments=segments,start_ns=start,done_ns=done))
 assert transfers[1]['done_ns']<=g['completed']['dma_poll_complete']<=g['consumer_start_ns']
 assert ceil(Fraction(done_fs,1000000))<=g['completed']['dirty_writeback_callback']
 assert g['consumer_start_ns']>=max(g['completed'].values())
 controls=0
 for delayed in sorted(KINDS):
  identity=g['identity'];expected={kind:0 for kind in KINDS}
  gate=CompletionGate(identity,expected)
  for kind in sorted(KINDS):
   t=(max(g['completed'].values())+1000) if kind==delayed else g['completed'][kind]
   gate.accept(kind,identity,0,t,'1')
  try: gate.release(g['consumer_start_ns'])
  except ValueError: controls+=1
  else: raise AssertionError('delayed real receipt failed to block')
  assert gate.release(max(gate.completed.values()))==max(gate.completed.values())
 reports.append(dict(branch=branch,issued_writebacks=issued,pending=pending,
                     writeback_now_fs=now_fs,writeback_done_fs=done_fs,
                     wait_ns=float(Fraction(done_fs-now_fs,1000000)),
                     DMA=transfers,delayed_actual_receipt_controls=controls,
                     consumer_start_ns=g['consumer_start_ns']))
out=dict(state='PASS_LIMITED_RUNTIME_RECEIPT_ORDER',branches=reports,
 completion_observation='CPU/writeback acknowledgement and NoC receive time are conservative receiver observations; raw Sniper drain and gateway DMA device times independently checked',
 limitations=['custom configured PCIe device model uses serialized queue0 and polling boundary at receive',
              'two CFG paths use service round slots; uncond consumes preceding same-shape PopNet delay profile',
              'NoC first pass is domain service; second pass applies PopNet feedback; no convergence claim',
              'one active NPU/HB and CPU0; no full layer cost coverage'],
 original_audit='INDEPENDENT_AUDIT.json')
(R/'RUNTIME_RECEIPT_AUDIT.json').write_text(json.dumps(out,indent=2))
files=[p for p in sorted(R.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
       and p.suffix not in ('.gz',) and p.name not in ('FINAL_MANIFEST.json','FINAL_DELIVERY.json')
       and p.stat().st_size<16*2**20]
manifest=[dict(file=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]
(R/'FINAL_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
with tarfile.open(R/'runtime_review.tar.gz','w:gz') as t:
 for p in files+[R/'FINAL_MANIFEST.json']:t.add(p,arcname=str(p.relative_to(R)))
a=R/'runtime_review.tar.gz'
(R/'FINAL_DELIVERY.json').write_text(json.dumps(dict(sha256=hashlib.sha256(a.read_bytes()).hexdigest(),bytes=a.stat().st_size,payloads=len(files)),indent=2))
print(json.dumps(out))

