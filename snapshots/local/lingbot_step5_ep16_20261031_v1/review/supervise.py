import pathlib,subprocess,json,hashlib,shutil,os,time,traceback,tarfile
R=pathlib.Path(__file__).resolve().parent;B=R.parent;os.umask(0o022)
def put(n,v):(R/n).write_text(json.dumps(v,indent=2))
try:
 freeze=json.loads((R/'FREEZE.json').read_text());assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in freeze.items())
 py='/mnt/sda1/h3240101068/lingbot_steps1_2_20261027_v1/venv/bin/python'
 with (R/'functional.log').open('w') as f:c=subprocess.run([py,str(R/'run_ep16.py')],stdout=f,stderr=subprocess.STDOUT,timeout=1800)
 put('FUNCTIONAL_EXIT.json',dict(returncode=c.returncode));assert c.returncode==0
 result=json.loads((R/'FUNCTIONAL_RESULT.json').read_text());assert result['status']=='PASS_LIMITED_EP16_FULL_ROUTE_SERIALIZATION_FFN_RESTORE'
 W=R/'popnet';W.mkdir(exist_ok=False);shutil.copy2(B/'swe_qwen3_legosim_16_layers_20261030_v3/noc_v3_6.gv',R/'noc_v3_6.gv');pop=B/'swe_qwen3_legosim_16_service_20261030_v1/popnet_xy_build/popnet'
 args=[str(pop),'-A','17','-c','1','-V','3','-B','8','-O','8','-F','4','-L','2000','-T','1000000000000','-r','1','-I','../bench.txt','-R','4','-D','../delayInfo.txt','-G',str(R/'noc_v3_6.gv'),'-P']
 put('POP_NET_BINDING.json',dict(args=args,executable_sha256=hashlib.sha256(pop.read_bytes()).hexdigest(),graph_sha256=hashlib.sha256((R/'noc_v3_6.gv').read_bytes()).hexdigest(),open_loop_trace=True,coupled_payload=False))
 put('STATUS.json',dict(state='RUNNING_POPNET_SELECTED_TRACE',records=result['noc_records'],whole_step5=False))
 with (R/'popnet.log').open('w') as f:c=subprocess.run(args,cwd=W,stdout=f,stderr=subprocess.STDOUT,timeout=600)
 put('POP_NET_EXIT.json',dict(returncode=c.returncode));assert c.returncode==0
 lines=(R/'delayInfo.txt').read_text().splitlines();records=json.loads((R/'NOC_RECORDS.json').read_text());assert len(lines)==len(records)>0
 put('POP_NET_RESULT.json',dict(status='PASS_LIMITED_SELECTED_REAL_BYTE_OPEN_LOOP_REPLAY',records=len(lines),delay_sha256=hashlib.sha256((R/'delayInfo.txt').read_bytes()).hexdigest(),source='same original dualCFG 64 queries each',full_step5=False,coupled=False))
 bad=[str(q.relative_to(R)) for q in R.rglob('*') if (q.is_file() and not q.stat().st_mode&4) or (q.is_dir() and q.stat().st_mode&5!=5)];assert not bad
 put('PERMISSION_AUDIT.json',dict(POSIX_other_read_traverse=True,cross_account_login=False))
 put('STATUS.json',dict(state='PASS_LIMITED_EP16_FUNCTIONAL_AND_SELECTED_POPNET',whole_step5=False,target_GPU_count=0,remaining=['AttentionTP16 exact O reduction','full target compute/host/HB/SRAM integration','coupled completion-driven full NoC DAG']))
except BaseException:
 put('FAILURE.json',dict(traceback=traceback.format_exc()));put('STATUS.json',dict(state='STOPPED_FAILURE_PRESERVED',whole_step5=False));raise
finally:
 members=[q for q in R.rglob('*') if q.is_file() and q.suffix!='.npy' and q.name!='review.tar.gz' and '__pycache__' not in q.parts and q.stat().st_size<20*2**20]
 manifest=[dict(file=str(q.relative_to(R)),bytes=q.stat().st_size,sha256=hashlib.sha256(q.read_bytes()).hexdigest()) for q in members];put('MANIFEST.json',manifest)
 with tarfile.open(R/'review.tar.gz','w:gz') as t:
  for q in members+[R/'MANIFEST.json']:t.add(q,arcname=str(q.relative_to(R)))
 put('DELIVERY.json',dict(archive_sha256=hashlib.sha256((R/'review.tar.gz').read_bytes()).hexdigest(),archive_bytes=(R/'review.tar.gz').stat().st_size,payloads=len(members),review_only=True))
