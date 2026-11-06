import sys,json,os,re
sys.path.insert(0,'/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim/tools')
import sniper_lib
R=os.path.dirname(os.path.abspath(__file__));version=int(sys.argv[1]) if len(sys.argv)>1 else 2;D=os.path.join(R,'drain_probe_run_v%d'%version)
exit=json.load(open(os.path.join(R,'DRAIN_PROBE_V%d_EXIT.json'%version)))
assert exit['returncode']==0 and exit['functional_file']
text=open(os.path.join(R,'DRAIN_PROBE_V%d.log'%version)).read();assert '*ERROR*' not in text and 'Assertion' not in text
acks={};drains=[]
for line in text.splitlines():
 m=re.search(r'MAINT_WRITE_ACK (\d+) (\d+) (\d+) (\d+)',line)
 if m:
  token,address,start,end=map(int,m.groups());assert token not in acks and end>=start;acks[token]=dict(address=address,start=start,end=end)
 m=re.search(r'MAINT_DRAIN (\d+) (\d+) (\d+) (\d+)',line)
 if m:
  issued,pending,now,done=map(int,m.groups());assert pending==0 and done>=now
  assert all(t in acks for t in range(1,issued+1))
  assert all(v['end']<=done for k,v in acks.items() if k<=issued)
  drains.append(dict(issued=issued,pending=pending,now_fs=now,done_fs=done,wait_fs=done-now))
assert len(drains)==2 and len(acks)>0
rows=[]
for a,b in [(100,101),(102,103),(103,104),(104,105),(110,111),(112,113),(113,114),(114,115),(120,121),(122,123),(124,125)]:
 r=sniper_lib.get_results(resultsdir=D,partial=('marker-%d-0'%a,'marker-%d-0'%b))['results']
 keys=['L1-D.loads','L1-D.load-misses','L1-D.evict-M','L2.evict-M','L3.evict-M','dram.writes','performance_model.elapsed_time','performance_model.nonidle_elapsed_time']
 metrics={k:(r[k][0] if isinstance(r[k],list) else r[k]) for k in keys if k in r};rows.append(dict(begin=a,end=b,metrics=metrics))
post={x['begin']:x for x in rows if x['begin'] in [104,114,124]}
assert post[104]['metrics']['L1-D.load-misses']>=3 and post[114]['metrics']['L1-D.load-misses']>=3
assert post[124]['metrics']['L1-D.load-misses']==0
out=dict(state='PASS_LIMITED_DIRECTORY_DRAIN_SMALL_PROBE',write_ack_count=len(acks),drains=drains,marker_metrics=rows,negative_control_no_maintenance_post_load_misses=0,scope='single CPU0, three cache lines across LLC sets8191/0/1; no NUCA or active directory collision; small native probe only',full_layer_runs=0,full_target_timing=False,full_steps_1_7=False)
open(os.path.join(R,'DIRECTORY_PROBE_V%d_AUDIT.json'%version),'w').write(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
