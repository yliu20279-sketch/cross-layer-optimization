from pathlib import Path
import json,sqlite3,time,traceback,shutil
R=Path(__file__).resolve().parent;deadline=time.monotonic()+139200
try:
 while not (R/'FINAL_DELIVERY.json').exists():
  if (R/'CONTROLLER_FAILURE.txt').exists():raise RuntimeError('controller failure before final delivery')
  if time.monotonic()>deadline:raise TimeoutError('supplemental ISA audit wait expired')
  time.sleep(10)
 original=json.loads((R/'FINAL_DELIVERY.json').read_text())
 if not original['state'].startswith('PASS_'):
  (R/'ISA_ALL_CORES_NOT_RUN.json').write_text(json.dumps(dict(reason=original)))
 else:
  results=[]
  for iteration in [1,2]:
   db=sqlite3.connect('file:'+str(R/f'case{iteration}/CPU_FINAL_STATS.sqlite3')+'?mode=ro',uri=True)
   rows=db.execute("select v.core,n.objectname,n.metricname,v.value from [values] v join names n using(nameid) join prefixes p using(prefixid) where p.prefixname='roi-end' and n.objectname in ('decoded_isa_nehalem_ok','decoded_isa_nehalem_rejected')").fetchall();db.close()
   assert rows and not any(v for core,o,n,v in rows if o=='decoded_isa_nehalem_rejected')
   supported={}
   for core,o,n,v in rows:
    if o=='decoded_isa_nehalem_ok':supported[str(core)]=supported.get(str(core),0)+v
   assert sum(supported.values())>0
   results.append(dict(round=iteration,supported_decoded_occurrences_by_core=supported,rejected_all_cores=0))
  (R/'ISA_ALL_CORES_AUDIT.json').write_text(json.dumps(dict(state='PASS_LIMITED_ALL_CORE_DECODED_ISA',rounds=results),indent=2))
  shutil.copy2(R/'FINAL_DELIVERY.json',R/'FINAL_BASE_DELIVERY.json')
  original['ISA_all_cores_verified']=True
  temporary=R/'FINAL_DELIVERY.tmp';temporary.write_text(json.dumps(original,indent=2));temporary.replace(R/'FINAL_DELIVERY.json')
except Exception:
 (R/'ISA_ALL_CORES_FAILURE.txt').write_text(traceback.format_exc())
 if (R/'FINAL_DELIVERY.json').exists():
  shutil.copy2(R/'FINAL_DELIVERY.json',R/'FINAL_PRE_SUPPLEMENT_FAILURE.json')
  (R/'FINAL_DELIVERY.json').write_text(json.dumps(dict(state='FAIL_ISA_SUPPLEMENTAL_AUDIT',full_model_pass=False)))
 raise
