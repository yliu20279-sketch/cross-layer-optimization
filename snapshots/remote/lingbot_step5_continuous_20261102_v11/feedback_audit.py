import pathlib,json,sys,time,csv,hashlib
R=pathlib.Path(sys.argv[1]);end=time.monotonic()+140000
while time.monotonic()<end:
 if (R/'DAG_AUDIT.json').exists():break
 if (R/'STATUS.json').exists() and json.loads((R/'STATUS.json').read_text())['state'].startswith('STOPPED'):raise RuntimeError('production failed, no feedback promotion')
 time.sleep(5)
else:raise TimeoutError('feedback audit wait budget')
results=[]
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for k in [1,2]:
 p=R/'run'/('noc_feedback_round%d.csv'%k);rows=list(csv.DictReader(p.open()));bench=(R/('case%d'%k)/'bench.txt').read_text().splitlines();assert len(rows)==len(bench)>0
 assert all(int(r['profile_applied'])==(0 if k==1 else 1) for r in rows)
 assert all(0<=int(r['src'])<16 and 0<=int(r['dst'])<16 and r['src']!=r['dst'] for r in rows)
 dp=R/'run'/('domain_service_round%d.csv'%k);n=0
 for r in csv.DictReader(dp.open()):
  assert int(r['complete'])>=int(r['start'])>=int(r['ready']);assert int(r['complete'])>=int(r['wire_complete'])>=int(r['host_complete']);n+=1
 assert n>0
 results.append(dict(round=k,horizontal_messages=len(rows),all_feedback_applied=k==2,first_round_without_feedback=k==1,domain_records=n,noc_csv_sha256=sha(p),domain_csv_sha256=sha(dp)))
config=json.loads((R/'config.yml').read_text());ram=[v for v in config['phase1'] if v['cmd'].endswith('/ramulator2')];assert len(ram)==16 and all(v['args'][2]=='1.25' for v in ram)
r=dict(state='PASS_LIMITED_ALL_HORIZONTAL_FEEDBACK_AND_DOMAIN_ORDER',rounds=results,DRAM_config_scale_ns=1.25,physical_calibration=False,scope='all horizontal records use previous feedback in round2; domain ordering only, not full CPU/DRAM independent numeric timing calibration',whole_step5=False);(R/'FEEDBACK_AUDIT.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
