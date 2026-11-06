import json,time,sqlite3,shutil,hashlib,traceback
from pathlib import Path
R=Path(__file__).resolve().parent;deadline=time.monotonic()+87500;rows=[]
try:
 for iteration in [1,2]:
  D=R/('case%d'%iteration);log=R/'run1'/('proc_r%d_p1_t0'%iteration)/'cpu.log'
  while True:
   # Tail only; never materialize a multi-GB CPU log.
   if log.exists():
    with log.open('rb') as f:f.seek(max(0,log.stat().st_size-4096));tail=f.read().decode(errors='replace')
    if (D/'CPU_PASS.json').exists() and '[SNIPER] End' in tail:break
   if (R/'RUN_EXIT.json').exists() and json.loads((R/'RUN_EXIT.json').read_text())['returncode']!=0:raise RuntimeError('native run failed before CPU final snapshot')
   if time.monotonic()>deadline:raise TimeoutError('CPU snapshot deadline')
   time.sleep(10)
  source=R/'sniper/sim.stats.sqlite3';target=D/'CPU_FINAL_STATS.sqlite3'
  # Phase2 is a separate barrier before round2 starts; snapshot while CPU is exited.
  a=sqlite3.connect(str(source));b=sqlite3.connect(str(target));a.backup(b);b.close();a.close()
  shutil.copy2(R/'sniper/sim.cfg',D/'CPU_FINAL_CONFIG.cfg')
  rows.append(dict(round=iteration,stats_sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
  (R/'CPU_STATS_SNAPSHOTS.json').write_text(json.dumps(rows,indent=2))
except Exception:(R/'CPU_STATS_SNAPSHOT_FAILURE.txt').write_text(traceback.format_exc());raise
