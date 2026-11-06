"""Resume own CPU job and finish connected validation independently of client."""
import os,pathlib,json,signal,time,subprocess,hashlib,sys
P=pathlib.Path(__file__).resolve().parent;py='/mnt/sda1/h3240101068/lingbot_steps1_2_20261027_v1/venv/bin/python'
assert json.loads((P/'SIMD_PRIMITIVE_RESULT.json').read_text())['bit_mismatches']==0
assert json.loads((P/'SIMD_GEMM_RESULT.json').read_text())['bit_mismatches']==0
old=str(P/'validate_full_kv.py').encode();found=[]
for proc in pathlib.Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 try:
  args=(proc/'cmdline').read_bytes().split(b'\0')
  if proc.stat().st_uid==os.getuid() and len(args)>1 and args[0]==py.encode() and args[1]==old:found.append(int(proc.name))
 except (FileNotFoundError,PermissionError):pass
assert len(found)<=1,found
chunks=list((P/'full_kv_attempt1').glob('*/*.npy'));receipt=dict(date='2026-10-30',reason='validated SIMD implementation accelerates same integer FDA semantics',old_owned_processes=found,preserved_chunks=len(chunks),preserved_bytes=sum(q.stat().st_size for q in chunks),new_source_sha256=hashlib.sha256((P/'validate_full_kv_simd.py').read_bytes()).hexdigest(),target_GPU_count=0)
(P/'CPU_RESUME_RECEIPT.json').write_text(json.dumps(receipt,indent=2))
for pid in found:os.kill(pid,signal.SIGTERM)
for _ in range(30):
 if not any(pathlib.Path('/proc',str(pid)).exists() for pid in found):break
 time.sleep(.2)
else:raise RuntimeError('old CPU process remains; refusing duplicate')
results=[]
for script,log,limit in [('validate_full_kv_simd.py','full_kv_simd.log',1800),('validate_connected_block_simd.py','connected_block.log',900)]:
 (P/'PIPELINE_STATUS.json').write_text(json.dumps(dict(state='RUNNING',stage=script,pid=os.getpid(),target_GPU_count=0),indent=2))
 with (P/log).open('w') as f:r=subprocess.run([py,str(P/script)],stdout=f,stderr=subprocess.STDOUT,timeout=limit)
 results.append(dict(script=script,exit_code=r.returncode))
 (P/'PIPELINE_EXITS.json').write_text(json.dumps(results,indent=2))
 if r.returncode:raise RuntimeError(results[-1])
(P/'PIPELINE_STATUS.json').write_text(json.dumps(dict(state='COMPLETE_NUMERICAL_RUNS',results=results,target_GPU_count=0),indent=2))
