"""Own L2 receipts only: input/accounting and pair to frozen existing RR."""
import csv,hashlib,json,math
from pathlib import Path
R=Path(__file__).resolve().parent
s=json.loads((R/'SOURCE_MANIFEST.json').read_text());m=json.loads((R/'MATRIX.json').read_text());b=json.loads((R/'BUILD.json').read_text())
assert m['status']=='PASS' and m['completed']==len(m['tasks'])==120
for name,expected in s['source_sha256'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==expected,name
for target in b['targets']:assert hashlib.sha256((R/f'obj{target["mode"]}/Vdut').read_bytes()).hexdigest()==target['binary_sha256']
cases={c['name']:c for c in s['cases']};rows=[];checks=0
ref=Path(s['baseline_matrix']['result_path'])
for run in m['runs']:
 t=run['task'];p=R/'results'/(run['name']+'.json');assert hashlib.sha256(p.read_bytes()).hexdigest()==run['sha256'];d=json.loads(p.read_text())
 rrpath=ref/(t['case']+'_'+t['arm']+'_b8.json');rrraw=rrpath.read_bytes();rr=json.loads(rrraw)
 assert len(d['waves'])==len(rr['waves'])==6
 read=write=bank=0
 for w,e,base in zip(d['waves'],cases[t['case']]['waves'],rr['waves']):
  checks+=1;payload=e['moe_payload_bytes'];gets=e['gets'];packets=payload//512
  assert w['stage']==e['stage']==base['stage']
  assert w['canonical_payload_hash']==base['canonical_payload_hash']
  assert w['packets']==packets+2*gets and w['gets_count']==gets
  assert w['c_flits']==w['cs_flits']==w['configuration_requests']==0
  assert w['m_flits']==packets*17+4*gets
  assert w['finish']==max(w['moe'],w['gets'])
  read+=payload//32;write+=payload//32+2*gets;bank+=2*gets
  rows.append(dict(case=t['case'],arm=t['arm'],stage=w['stage'],rr_joint=base['finish'],priority_joint=w['finish'],rr_gets=base['gets'],priority_gets=w['gets'],rr_p99=base['gets_p99'],priority_p99=w['gets_p99'],rr_moe=base['moe'],priority_moe=w['moe'],rr_wait=base['gets_injection_wait_sum'],priority_wait=w['gets_injection_wait_sum'],priority_sha256=run['sha256'],rr_sha256=hashlib.sha256(rrraw).hexdigest()))
 assert (d['read_flits'],d['write_flits'],d['bank_flits'])==(read,write,bank)
 assert (d['read_flits'],d['write_flits'],d['bank_flits'])==(rr['read_flits'],rr['write_flits'],rr['bank_flits'])
with (R/'PAIRED_PHASES.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
summary=[]
for arm in ['mesh','hiband_FG','hiband_GB','hiband_LB']:
 vals=[];p99=[];moe=[]
 for case in cases:
  group=[x for x in rows if x['case']==case and x['arm']==arm]
  vals.append(sum(x['rr_joint'] for x in group)/sum(x['priority_joint'] for x in group))
  p99.append(max(x['rr_p99'] for x in group)/max(x['priority_p99'] for x in group))
  moe.append(sum(x['rr_moe'] for x in group)/sum(x['priority_moe'] for x in group))
 gm=lambda x:math.exp(sum(map(math.log,x))/len(x))
 summary.append(dict(arm=arm,cases=len(vals),joint_geomean_speedup=gm(vals),max_phase_p99_geomean_ratio=gm(p99),moe_geomean_speedup=gm(moe),wins=sum(x>1+1e-12 for x in vals),losses=sum(x<1-1e-12 for x in vals)))
audit=dict(status='PASS_L2_120_RUNS_720_PHASES_PAYLOAD_WIRE_AND_SRAM',runs=120,phase_checks=checks,source_digest=s['source_digest'],paired_rr_path=str(ref),summary=summary,
 scope='Six development cases already inspected before; no held-out claim. Fixed type priority only at NI/router. Same input, finite synthetic GetS, endpoint model and SRAM. No synthesis or full application claim.')
(R/'AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit,indent=2))
