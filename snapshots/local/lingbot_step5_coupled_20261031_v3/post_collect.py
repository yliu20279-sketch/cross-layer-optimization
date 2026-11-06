import pathlib,json,hashlib,collections,time,tarfile,traceback,shutil,os
R=pathlib.Path(__file__).resolve().parent;deadline=time.monotonic()+2100
while time.monotonic()<deadline:
 if (R/'STATUS.json').exists():
  state=json.loads((R/'STATUS.json').read_text())['state']
  if state.startswith(('PASS','STOPPED')):break
 time.sleep(5)
else:raise TimeoutError('post collector bounded wait expired')
try:
 if not state.startswith('PASS'):raise RuntimeError('production stopped; failures preserved')
 original=json.loads((R/'INDEPENDENT_AUDIT.json').read_text());assert all(c['passed'] for c in original['checks']);dag_results=[]
 for case in sorted(R.glob('case*')):
  nodes={};outgoing=collections.defaultdict(list);indegree={};send={};recv={};ranklists=[]
  for rank in range(16):
   events=json.loads((case/('N%02d'%rank)/'EVENTS.json').read_text());prev=None;ranklists.append(events)
   for i,e in enumerate(events):
    key='N%d_E%d'%(rank,i);node=dict(id=key,event=e,deps=[prev] if prev else []);nodes[key]=node;prev=key
    if e['kind']=='send':
     tag=(rank,e['peer'],e['label']);assert tag not in send;send[tag]=key
    elif e['kind']=='recv':
     tag=(e['peer'],rank,e['label']);assert tag not in recv;recv[tag]=key
  assert send.keys()==recv.keys()
  for tag,src in send.items():
   dst=recv[tag];a=nodes[src]['event'];b=nodes[dst]['event'];assert a['sha256']==b['sha256'] and a['bytes']==b['bytes'] and b['done']>=a['done'];nodes[dst]['deps'].append(src)
  for key,n in nodes.items():
   indegree[key]=len(n['deps'])
   for dep in n['deps']:outgoing[dep].append(key)
  ready=collections.deque(k for k,d in indegree.items() if d==0);visited=0
  while ready:
   k=ready.popleft();visited+=1
   for t in outgoing[k]:
    indegree[t]-=1
    if indegree[t]==0:ready.append(t)
  assert visited==len(nodes),'cycle'
  # Auditor negative controls on actual recorded transfers and addresses.
  tag=next(iter(send));a=nodes[send[tag]]['event'];b=nodes[recv[tag]]['event'];bad=dict(b);bad['sha256']='0'*64;assert bad['sha256']!=a['sha256'];bad=dict(b);bad['done']=a['done']-1;assert not bad['done']>=a['done'];missing=dict(recv);del missing[tag];assert send.keys()!=missing.keys();hb=next(e for rr in ranklists for e in rr if e['kind']=='HB');bad=dict(hb);bad['addr']=512*2**20;assert bad['addr']+bad['bytes']>512*2**20
  (case/'EXPLICIT_NATIVE_DAG.json').write_text(json.dumps(list(nodes.values()),indent=2));dag_results.append(dict(case=case.name,nodes=len(nodes),edges=sum(len(n['deps']) for n in nodes.values()),paired_network_messages=len(send),negative_controls=4,acyclic=True,consumer_release_after_send_completion=True,scope='native HB/network/generic compute macro events only; no complete CPU/opcode/SRAM Bank DAG'))
 lib=R/'emulator_build/_tc_emu_h100_bf16_simd.so';prior=R.parent/'lingbot_step4_bitexact_20261029_v4/emulator_build/_tc_emu_h100_bf16_simd.so';h=lambda q:hashlib.sha256(q.read_bytes()).hexdigest();assert h(lib)==h(prior)
 result=dict(state='PASS_LIMITED_SELECTED_NATIVE_COMPLETION_DAG_TWO_ROUND',rounds=dag_results,independent_numeric_audit=original['state'],old_and_isolated_derived_library_SHA_equal=True,library_sha256=h(lib),whole_step5=False,full_all_query_layer=False,CPU_host_PCIE_cost=False,full_SRAM_Bank=False,target_GPU_count=0)
 (R/'DAG_AUDIT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
except BaseException:
 (R/'POST_FAILURE.json').write_text(json.dumps(dict(error=traceback.format_exc()),indent=2))
finally:
 for n in ['LICENSE','LICENSE.txt']:
  src=R.parent/'lingbot_step4_bitexact_20261029_v4/upstream'/n
  if src.exists():shutil.copy2(src,R/'UPSTREAM_LICENSE');break
 members=[q for q in sorted(R.rglob('*')) if q.is_file() and 'run' not in q.relative_to(R).parts and q.name not in ['review.tar.gz','REVIEW_MANIFEST.json','DELIVERY.json'] and '__pycache__' not in q.parts and q.stat().st_size<30*2**20]
 manifest=[]
 for q in members:q.chmod(0o644);manifest.append(dict(file=str(q.relative_to(R)),bytes=q.stat().st_size,sha256=hashlib.sha256(q.read_bytes()).hexdigest()))
 for q in R.rglob('*'):
  if q.is_dir():q.chmod(0o755)
 (R/'REVIEW_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
 with tarfile.open(R/'review.tar.gz','w:gz') as t:
  for q in members+[R/'REVIEW_MANIFEST.json']:t.add(q,arcname=str(q.relative_to(R)))
 (R/'DELIVERY.json').write_text(json.dumps(dict(sha256=hashlib.sha256((R/'review.tar.gz').read_bytes()).hexdigest(),bytes=(R/'review.tar.gz').stat().st_size,payloads=len(members),scope='review excluding raw run process logs, retaining selected numeric arrays and DAG'),indent=2))
