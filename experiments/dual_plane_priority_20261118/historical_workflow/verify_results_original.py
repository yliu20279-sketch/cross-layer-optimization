"""Independent local audit of read-only L2 results, including frozen RR refs."""
from collections import Counter
import csv,hashlib,json,math,argparse
from pathlib import Path
R=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--full',action='store_true');args=parser.parse_args()
prefix='FULL_' if args.full else '';expected_total=120 if args.full else 24
s=json.loads((R/(prefix+'LATEST_STATUS.json')).read_text(encoding='utf-8'))
base=json.loads((R.parent/'dual_plane_rtl_followup_20261118/REMOTE_SNAPSHOT.json').read_text(encoding='utf-8'))
src=json.loads(s['files']['SOURCE_MANIFEST.json']);b=json.loads(s['files']['BUILD.json']);m=json.loads(s['files'].get('MATRIX.json','{}'))
cases={c['name']:c for c in src['cases']};fail=[];count=0
def check(test,label):
 global count
 count+=1
 if not test:fail.append(label)
def savecsv(name,rows):
 if not rows:return
 with (R/(prefix+name)).open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
for name,h in s.get('source_actual',{}).items():check(h==src['source_sha256'][name],'source '+name)
for target in b.get('targets',[]):check(s.get('binary_actual',{}).get(str(target['mode']))==target['binary_sha256'],'binary '+str(target['mode']))
check(b['status']=='PASS','regression gate')
check(m.get('source_digest')==src['source_digest'],'matrix source')
check(m.get('image')==src['image'],'matrix image')
tasks=m.get('tasks',[]);check(len(tasks)==expected_total,'expected task count');check(len({(t['case'],t['arm']) for t in tasks})==expected_total,'no duplicate tasks')
check({t['case'] for t in tasks}==set(cases),'frozen case coverage')
phase_rows=[];run_rows=[];results={}
for run in m.get('runs',[]):
 if run['status']!='PASS':continue
 t=run['task'];name=run['name'];entry=s['results'][name]
 check(hashlib.sha256(entry['text'].encode()).hexdigest()==run['sha256']==entry['sha256'],name+' output SHA')
 d=json.loads(entry['text']);refname=t['case']+'_'+t['arm']+'_b8';ref=s['rr_reference'][refname];rr=json.loads(ref['text'])
 check(ref['sha256']==base['completed_outputs'][refname]['sha256'],name+' immutable RR source')
 check(d['status']=='PASS_RTL_DELIVERY_PAYLOAD_AND_SRAM',name+' delivery')
 check((d['arm'],d['dual'],d['hiband_mode'],d['bank_latency'],d['clock_ns'])==(t['arm'],0,t['hiband'],8,1),name+' parameters')
 check(len(d['waves'])==len(rr['waves'])==6,name+' six phases')
 check(t['policy']=='type_priority',name+' policy')
 services=[0,0,0]
 for w,refw,cw in zip(d['waves'],rr['waves'],cases[t['case']]['waves']):
  check(w['stage']==cw['stage']==refw['stage'],name+' phase order')
  check(w['canonical_payload_hash']==refw['canonical_payload_hash'],name+' paired payload')
  payload=cw['moe_payload_bytes'];gets=cw['gets']
  check(w['gets_count']==gets and w['packets']==payload//512+2*gets,name+' packet conservation')
  check(w['m_flits']==payload//512*17+gets*4,name+' wire conservation')
  check(w['c_flits']==w['cs_flits']==w['configuration_requests']==0,name+' no extra network')
  check(w['finish']==max(w['gets'],w['moe']),name+' join')
  services[0]+=payload//32;services[1]+=payload//32+2*gets;services[2]+=gets*2
  phase_rows.append(dict(case=t['case'],arm=t['arm'],stage=w['stage'],rr_join=refw['finish'],priority_join=w['finish'],rr_gets=refw['gets'],priority_gets=w['gets'],rr_p99=refw['gets_p99'],priority_p99=w['gets_p99'],rr_moe=refw['moe'],priority_moe=w['moe'],rr_ni_wait=refw['gets_injection_wait_sum'],priority_ni_wait=w['gets_injection_wait_sum']))
 check([d['read_flits'],d['write_flits'],d['bank_flits']]==services,name+' SRAM conservation')
 check([rr['read_flits'],rr['write_flits'],rr['bank_flits']]==services,name+' same SRAM budget')
 run_rows.append(dict(case=t['case'],arm=t['arm'],rr_join_sum=sum(w['finish'] for w in rr['waves']),priority_join_sum=sum(w['finish'] for w in d['waves']),
  join_speedup=sum(w['finish'] for w in rr['waves'])/sum(w['finish'] for w in d['waves']),
  moe_speedup=sum(w['moe'] for w in rr['waves'])/sum(w['moe'] for w in d['waves']),max_phase_p99_ratio=max(w['gets_p99'] for w in rr['waves'])/max(w['gets_p99'] for w in d['waves']),
  output_sha256=entry['sha256'],rr_sha256=ref['sha256']))
 results[t['case'],t['arm']]=d
savecsv('INDEPENDENT_PAIRED_PHASES.csv',phase_rows);savecsv('INDEPENDENT_PAIRED_RUNS.csv',run_rows)
summary=[]
gm=lambda xs:math.exp(sum(map(math.log,xs))/len(xs))
for arm in ['mesh','hiband_FG','hiband_GB','hiband_LB']:
 rows=[x for x in run_rows if x['arm']==arm]
 if not rows:continue
 summary.append(dict(arm=arm,n=len(rows),join_geomean_speedup=gm([x['join_speedup'] for x in rows]),moe_geomean_speedup=gm([x['moe_speedup'] for x in rows]),max_phase_p99_geomean_ratio=gm([x['max_phase_p99_ratio'] for x in rows]),wins=sum(x['join_speedup']>1+1e-12 for x in rows),losses=sum(x['join_speedup']<1-1e-12 for x in rows)))
savecsv('INDEPENDENT_SUMMARY.csv',summary)
# Development diagnostic: does the former dual-RR still beat a priority baseline?
dual_rows=[]
for name,c in cases.items():
 if (name,'mesh') not in results:continue
 old=base['completed_outputs'][name+'_dual_b8']['data'];new=results[name,'mesh']
 check([x['canonical_payload_hash'] for x in old['waves']]==[x['canonical_payload_hash'] for x in new['waves']],name+' dual-v-priority payload')
 dual_rows.append(dict(case=name,priority_mesh_sum=sum(x['finish'] for x in new['waves']),old_dual_rr_sum=sum(x['finish'] for x in old['waves']),dual_rr_over_priority_mesh_speedup=sum(x['finish'] for x in new['waves'])/sum(x['finish'] for x in old['waves'])))
savecsv('DUAL_RR_VS_PRIORITY_MESH.csv',dual_rows)
audit=dict(status=(f'PASS_COMPLETE_{expected_total}' if m.get('status')=='PASS' and len(run_rows)==expected_total else 'PASS_PARTIAL_SNAPSHOT') if not fail else 'FAIL',observed_at=s['observed_at'],source_digest=src['source_digest'],checks=count,failures=fail,
 completed=m.get('completed',0),runs_checked=len(run_rows),phase_checks=len(phase_rows),matrix_status=m.get('status'),summary=summary,
 old_dual_rr_vs_priority_mesh_geomean_speedup=gm([x['dual_rr_over_priority_mesh_speedup'] for x in dual_rows]) if dual_rows else None,
 scope=f'{len(cases)} frozen development cases, communication phase sums only. Static priority can hurt MoE. Old dual-RR vs priority-Mesh changes arbitration as well as planes; diagnostic only. No synthesis, end-to-end or held-out claim.',
 retained_failures=['Bootstrap missing include path, no matrix started','SV timing probe priority assertion failed; root not confirmed. Independent C++ probe and new common C++ regressions passed.'])
(R/(prefix+'INDEPENDENT_AUDIT.json')).write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(audit,ensure_ascii=False,indent=2))
if fail:raise SystemExit(1)
