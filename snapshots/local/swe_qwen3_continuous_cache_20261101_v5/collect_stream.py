import json,time,subprocess,hashlib,tarfile,traceback,sys
from pathlib import Path
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R));deadline=time.monotonic()+90500
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8*1024**2):h.update(b)
 return h.hexdigest()
try:
 for n,h in json.loads((R/'ADDITIONAL_AUDITOR_FREEZE.json').read_text()).items():assert sha(R/n)==h
 while not (R/'RUN_EXIT.json').exists():
  if time.monotonic()>deadline:raise TimeoutError('native exit wait')
  time.sleep(10)
 status=json.loads((R/'RUN_EXIT.json').read_text());assert status['returncode']==0 and status['reason'] is None,status
 while not (R/'RAW_ORACLE_AUDIT.json').exists() or not (R/'case2/CPU_FINAL_STATS.sqlite3').exists():
  assert not (R/'RAW_ORACLE_FAILURE.txt').exists() and not (R/'CPU_STATS_SNAPSHOT_FAILURE.txt').exists()
  if time.monotonic()>deadline:raise TimeoutError('strict audit/snapshot wait')
  time.sleep(10)
 for name in ['audit_clock.py','audit_cache_stream.py']:
  with (R/(name+'.log')).open('w') as f:c=subprocess.run(['python3',str(R/name)],stdout=f,stderr=subprocess.STDOUT,timeout=3600)
  assert c.returncode==0,(name,c.returncode)
 from validate_lowering import validate
 rounds=[validate(R,i) for i in [1,2]]
 out=dict(state='PASS_LIMITED_FULL_TWO_LAYER_CPU_FP32_SRAM_REVIEW',rounds=rounds,original_BF16=True,host_GiB=128,HB_GiB=8,GPU_differences='retained',cache_chain='PASS_LIMITED_FULL_TWO_LAYER_CACHE_AND_ALIAS_CHAIN',dynamic_reclamation=False,full_target_timing=False,full_steps_1_7=False)
 (R/'INDEPENDENT_AUDIT.json').write_text(json.dumps(out,indent=2))
 cache=json.loads((R/'CACHE_CHAIN_AUDIT.json').read_text())
 (R/'REMOTE_RAW_CPU_LOGS.json').write_text(json.dumps(dict(scope='complete raw logs retained on113; all ACKs/CPU transport times audited in one pass; compact ledger is a derivative',files=[dict(path=v['raw_CPU_log'],bytes=v['raw_CPU_log_bytes'],sha256=v['raw_CPU_log_sha256']) for v in cache['rounds']]),indent=2))
 members={p for p in R.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name not in ['EXP16_ALL_FP32.bin','SAFE_MANIFEST.json','SAFE_DELIVERY_STATUS.json','DELIVERY_STATUS.json','cpu.log','collect_stream.py.log']}
 members.update(p for p in (R/'oracle_cpu').iterdir() if p.is_file() and p.suffix in ['.json','.bin'])
 manifest=[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(members)]
 (R/'SAFE_MANIFEST.json').write_text(json.dumps(manifest,indent=2));archive=R.parent/(R.name+'_SAFE_REVIEW.tar.gz')
 with tarfile.open(archive,'w:gz',dereference=True) as t:
  for p in sorted(members)+[R/'SAFE_MANIFEST.json']:t.add(p,arcname=R.name+'/'+str(p.relative_to(R)))
 delivery=dict(state='PASS_LIMITED_FULL_FUNCTIONAL_CPU_FP32_SRAM_SAFE_REVIEW',archive=str(archive),bytes=archive.stat().st_size,sha256=sha(archive),members=len(manifest),scope='all numerical/NoC/clock/SRAM evidence plus CPU gate ledger/final SQLite; multi-GB raw CPU ACK logs and16GiB math table remain on113 with full SHA; local review cannot claim full raw CPU ACK replay',full_steps_1_7=False)
 (R/'SAFE_DELIVERY_STATUS.json').write_text(json.dumps(delivery,indent=2));delivery['state']=out['state'];(R/'DELIVERY_STATUS.json').write_text(json.dumps(delivery,indent=2));print(json.dumps(out),flush=True)
except Exception:
 (R/'STREAM_COLLECTOR_FAILURE.txt').write_text(traceback.format_exc());raise
