"""Bounded build -> small probe -> strict audit -> review archive. Never launch full layers."""
import os,time,json,subprocess,hashlib,tarfile,shutil
from pathlib import Path
R=Path(__file__).resolve().parent;pid=int(os.environ.get('SWE_BUILD_PID','2097178'));started=time.time();gate=R/('FINAL_BUILD_PID.json' if (R/'FINAL_BUILD_PID.json').exists() else 'ORIGINAL_BUILD_DEPENDENCY.json');result=dict(state='WAITING_ISOLATED_BUILD',full_steps_1_7=False,full_native_layers=0)
(R/'DIRECTORY_FINISH_STATUS.json').write_text(json.dumps(result,indent=2))
try:
 while Path('/proc/%d'%pid).exists():
  if time.time()-started>1300:raise RuntimeError('build supervisor wait bound reached; no probe launched')
  time.sleep(5)
 p=R/'DRAIN_BUILD_EXIT.json';assert p.stat().st_mtime>=gate.stat().st_mtime
 build=json.loads(p.read_text());assert build['state']=='BUILD_ONLY_NOT_FUNCTIONAL_PASS',build
 with (R/'DIRECTORY_FINISH_PROBE.log').open('w') as f:c=subprocess.run(['python3',str(R/'run_drain_probe.py'),'5'],stdout=f,stderr=subprocess.STDOUT,timeout=210)
 assert c.returncode==0
 with (R/'DIRECTORY_FINISH_AUDIT.log').open('w') as f:c=subprocess.run(['python2',str(R/'audit_directory_probe.py'),'5'],stdout=f,stderr=subprocess.STDOUT,timeout=60)
 assert c.returncode==0,'strict cache/drain audit did not pass; inspect preserved logs'
 result.update(state='PASS_LIMITED_SMALL_NATIVE_DIRECTORY_PROBE',audit='DIRECTORY_PROBE_V5_AUDIT.json')
except Exception as e:result.update(state='NOT_PROMOTED_DIRECTORY_CANDIDATE',reason=str(e))
result.update(elapsed_seconds=time.time()-started,full_target_timing=False,full_steps_1_7=False,full_native_layers=0)
(R/'DIRECTORY_FINISH_STATUS.json').write_text(json.dumps(result,indent=2))
# Materialized bounded review: no full model, math tables, ELF or trace directories.
D=R/('review_v4'+os.environ.get('SWE_REVIEW_SUFFIX',''));D.mkdir(exist_ok=False)
files=[p for p in R.iterdir() if p.is_file() and p.suffix in ['.json','.py','.cpp','.h','.md','.log']]
files += [p for p in (R/'control_replay_v2').iterdir() if p.is_file() and p.suffix in ['.json','.jsonl','.bin']]
S=R/'sniper_drain_candidate'
for name in ['common/system/software_maintenance_tracker.h','common/system/magic_server.cc','common/core/memory_subsystem/memory_manager_base.h','common/core/memory_subsystem/memory_manager_fast.h','common/core/memory_subsystem/parametric_dram_directory_msi/memory_manager.h','common/core/memory_subsystem/parametric_dram_directory_msi/memory_manager.cc','common/core/memory_subsystem/parametric_dram_directory_msi/cache_cntlr.h','common/core/memory_subsystem/parametric_dram_directory_msi/cache_cntlr.cc','common/core/memory_subsystem/pr_l1_pr_l2_dram_directory_msi/shmem_msg.h','common/core/memory_subsystem/pr_l1_pr_l2_dram_directory_msi/shmem_msg.cc','common/core/memory_subsystem/pr_l1_pr_l2_dram_directory_msi/dram_directory_cntlr.h','common/core/memory_subsystem/pr_l1_pr_l2_dram_directory_msi/dram_directory_cntlr.cc','common/core/memory_subsystem/dram/dram_cntlr_interface.cc']:files.append(S/name)
for folder in sorted(R.glob('drain_probe_run_v*')):
 for name in ['sim.cfg','sim.info','sim.out','sim.stats.sqlite3','sim.scripts.py','FUNCTIONAL_PASS.txt']:
  if (folder/name).is_file():files.append(folder/name)
files=list(dict.fromkeys(files));assert sum(p.stat().st_size for p in files)<256*1024**2
manifest={}
for p in files:
 name=str(p.relative_to(R));q=D/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);manifest[name]=dict(bytes=q.stat().st_size,sha256=hashlib.sha256(q.read_bytes()).hexdigest());os.chmod(q,0o644)
(D/'REVIEW_MANIFEST.json').write_text(json.dumps(manifest,indent=2));os.chmod(D/'REVIEW_MANIFEST.json',0o644)
A=R.parent/(R.name+'_REVIEW'+os.environ.get('SWE_REVIEW_SUFFIX','')+'.tar.gz')
with tarfile.open(A,'w:gz') as t:t.add(D,arcname=R.name,recursive=True)
out=dict(state=result['state'],archive=str(A),bytes=A.stat().st_size,sha256=hashlib.sha256(A.read_bytes()).hexdigest(),members=len(manifest),full_steps_1_7=False)
(R/'REVIEW_DELIVERY_STATUS.json').write_text(json.dumps(out,indent=2));os.chmod(A,0o644);print(json.dumps(out))
