import json,os,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;source=Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/interchiplet');dest=R/'interchiplet'
assert (source/'includes/pipe_comm.h').is_file()
if not dest.exists():os.symlink(str(source),str(dest),target_is_directory=True)
assert dest.resolve()==source
for n in ['DRAIN_BUILD_EXIT.json','DRAIN_BUILD_V2.log']:shutil.copy2(R/n,R/('FAILED_MISSING_PIPE_HEADER_'+n))
(R/'ORIGINAL_BUILD_DEPENDENCY.json').write_text(json.dumps(dict(source=str(source),binding=str(dest),scope='read-only source dependency for original relative include; shared tree not modified'),indent=2))
with (R/'DIRECTORY_FULL_ABI_BUILD_V3.log').open('w') as f:p=subprocess.Popen(['python3',str(R/'build_drain.py'),'--force'],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps(dict(build_pid=p.pid)))
