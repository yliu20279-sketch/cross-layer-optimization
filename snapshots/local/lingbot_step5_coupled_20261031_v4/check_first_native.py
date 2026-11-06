import pathlib,json,csv,hashlib,collections
R=pathlib.Path(__file__).resolve().parent;D=R/'case1';send={};recv={};bank=[]
for rank in range(16):
 q=D/('N%02d'%rank);ev=json.loads((q/'EVENTS.json').read_text());s=json.loads((q/'SRAM_SUMMARY.json').read_text());sizes=[x['bytes'] for x in ev if x['kind']=='HB'];assert s['read_bytes']==s['write_bytes']==sum(sizes);assert s['bank_service_cycles']==sum(2*((n+255)//256) for n in sizes);assert s['chunks']==sum((n+65535)//65536 for n in sizes);assert s['actual_peak_staging_bytes']==min(65536,max(sizes));bank.append(s)
 for e in ev:
  if e['kind']=='send':send[(rank,e['peer'],e['label'])]=e
  if e['kind']=='recv':recv[(e['peer'],rank,e['label'])]=e
assert send.keys()==recv.keys()
for k,a in send.items():b=recv[k];assert b['done']>=a['done'] and b['sha256']==a['sha256'] and b['bytes']==a['bytes']
rows=list(csv.DictReader((R/'run/noc_feedback_round1.csv').open()));assert len(rows)==len((D/'bench.txt').read_text().splitlines());assert all(int(r['profile_applied'])==0 for r in rows)
for r in csv.DictReader((R/'run/domain_service_round1.csv').open()):assert int(r['complete'])>=int(r['start'])>=int(r['ready']) and int(r['complete'])>=int(r['wire_complete'])>=int(r['host_complete'])
r=dict(state='PASS_LIMITED_FIRST_ROUND_HB_SRAM_AND_NATIVE_FINISH_DEPENDENCIES',all16BankCounters=True,native_messages=len(send),PopNet_records=len(rows),total_staging_read_bytes=sum(s['read_bytes'] for s in bank),total_staging_write_bytes=sum(s['write_bytes'] for s in bank),total_Bank_cycles=sum(s['bank_service_cycles'] for s in bank),whole_step5=False);(R/'PHASE1_EXTRA_AUDIT.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
