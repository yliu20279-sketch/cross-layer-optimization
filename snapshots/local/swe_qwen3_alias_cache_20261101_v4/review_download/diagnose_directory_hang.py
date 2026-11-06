import os,signal,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent;S=R/'sniper_drain_candidate';targets=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:args=(p/'cmdline').read_bytes().split(b'\0');args=[x.decode(errors='replace') for x in args if x]
 except (OSError,PermissionError):continue
 if str(R/'drain_probe_run_v2') in ' '.join(args) or (str(R/'run_drain_probe.py') in args and args[-1]=='2'):
  if int(p.name)!=os.getpid():targets.append(dict(pid=int(p.name),args=args))
(R/'DIRECTORY_PROBE_V2_STOP.json').write_text(json.dumps(dict(reason='missing final receipt and prolonged wait after SSH interruption; preserve implementation failure, not numerical PASS',targets=targets,stopped=time.time()),indent=2))
for x in targets:
 try:os.kill(x['pid'],signal.SIGTERM)
 except ProcessLookupError:pass
for x in targets:
 try:
  if Path('/proc/%d'%x['pid']).exists():os.kill(x['pid'],signal.SIGKILL)
 except ProcessLookupError:pass
# Ensure copied dependency files track the candidate, not the source checkout.
old='/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim';n=0
for folder in ['common','standalone']:
 for p in (S/folder).rglob('*.d'):
  text=p.read_text()
  if old in text:p.write_text(text.replace(old,str(S)));n+=1
# Add phase diagnostics to distinguish locking from missing directory callbacks.
p=S/'common/system/magic_server.cc';s=p.read_text();s=s.replace('            Core* core = Sim()->getCoreManager()->getCoreFromID(core_id);','            fprintf(stderr,"MAINT_MAGIC_ENTER\\n");\n            Core* core = Sim()->getCoreManager()->getCoreFromID(core_id);');s=s.replace('            SubsecondTime now = core->getPerformanceModel()->getElapsedTime();','            fprintf(stderr,"MAINT_BEFORE_CPU_TIME\\n");\n            SubsecondTime now = core->getPerformanceModel()->getElapsedTime();\n            fprintf(stderr,"MAINT_AFTER_CPU_TIME\\n");');s=s.replace('            SubsecondTime done = mm->drainWritebacksForSoftwareMaintenance(now);','            fprintf(stderr,"MAINT_BEFORE_DRAIN\\n");\n            SubsecondTime done = mm->drainWritebacksForSoftwareMaintenance(now);\n            fprintf(stderr,"MAINT_AFTER_DRAIN\\n");');s=s.replace('            core->getPerformanceModel()->queuePseudoInstruction(new SyncInstruction(done, SyncInstruction::PTHREAD_BARRIER));','            fprintf(stderr,"MAINT_BEFORE_SYNC\\n");\n            core->getPerformanceModel()->queuePseudoInstruction(new SyncInstruction(done, SyncInstruction::PTHREAD_BARRIER));\n            fprintf(stderr,"MAINT_AFTER_SYNC\\n");');p.write_text(s)
with (R/'DIRECTORY_DIAGNOSTIC_BUILD.log').open('w') as f:p=subprocess.Popen(['python3',str(R/'build_drain.py')],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps(dict(stopped=len(targets),dependency_files_rebound=n,build_pid=p.pid)))
