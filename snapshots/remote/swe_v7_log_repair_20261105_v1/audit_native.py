from pathlib import Path
import json,csv,re,sys,hashlib
r=Path(__file__).resolve().parent
sys.path.insert(0,str(r))
from strict_parser import audit
p=r/'endpoint_positive_v2'
assert json.loads((p/'RUN_EXIT.json').read_text())['returncode']==0
statuses=list(map(int,re.findall(r'terminate with status = (\d+)',(p/'RUN.log').read_text())))
assert len(statuses)==10 and not any(statuses)
rounds=[]
for iteration in [1,2]:
 d=p/f'case{iteration}'
 assert json.loads((d/'CPU_TEARDOWN_PASS.json').read_text())['state']=='PASS_EMPTY_ARENA_ACK'
 assert json.loads((d/'ENDPOINT_ROOT_PASS.json').read_text())['teardown_ack']
 for phase in ['prefill','decode']:assert (d/f'{phase}_CPU_ACTUAL.bin').read_bytes()==bytes(range(32))
 proc=p/'run1'/f'proc_r{iteration}_p1_t0'
 events=(proc/'maintenance.events').read_text().splitlines(True)
 result=audit(events);assert result['acks']>0 and result['drains']>0
 drains=[int(x.split()[4]) for x in events if x.startswith('MAINT_DRAIN ')]
 cursor=0;last=0;checks=0
 for line in (proc/'cpu.log').read_text().splitlines():
  if 'MAINT_AFTER_DRAIN' in line:
   last=drains[cursor];cursor+=1
  m=re.search(r'\[INTERCMD\] (?:READ|WRITE) (\d+) ',line)
  if m:
   assert int(m[1])*400000>=last
   checks+=1
 assert cursor==len(drains) and checks>0
 feedback=list(csv.DictReader((p/'run1'/f'noc_feedback_round{iteration}.csv').open()))
 assert feedback and (iteration==1 or all(int(x['profile_applied'])==1 for x in feedback))
 rounds.append(dict(round=iteration,events=result,clock_checks=checks,feedback=len(feedback)))
n=r/'endpoint_negative'
assert json.loads((n/'RUN_EXIT.json').read_text())['reason'].startswith('child_failure')
assert 'teardown with live ownership' in (n/'run1/proc_r1_p1_t0/cpu.log').read_text()
assert not (n/'case1/CPU_TEARDOWN_PASS.json').exists()
kv={}
for model in ['qwen3','qwen15']:
 q=r/f'{model}_precision_probe'
 assert json.loads((q/'RESULT.json').read_text())['status']=='PASS_LIMITED_NATIVE_KV_PROBE'
 rows=list(csv.reader((q/'KV_BATCH.csv').open()))
 start=max(float(x[1]) for x in rows if x[0]=='issue')
 ends=[float(x[1]) for x in rows if x[0]=='complete']
 assert min(ends)>start
 kv[model]=dict(accepted=start,callbacks=ends,overlap_native_clock=min(ends)-start,permission_denials=6)
out=dict(status='PASS_LIMITED_NATIVE_ENDPOINT_AND_KV_CALLBACK_WINDOWS',rounds=rounds,child_statuses=statuses,leak_rejected=True,kv=kv,full_two_layer_model=False,formal_matrix_runs=0,bank_internal_overlap_certified=False)
(r/'NATIVE_AUDIT.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
