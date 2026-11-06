from pathlib import Path
import subprocess,json
r=Path(__file__).resolve().parent
with (r/'sniper_build_isa.log').open('w') as f:
 for folder in ['common','standalone']:
  p=subprocess.run(['make','-j4','-C',str(r/'sniper'/folder)],stdout=f,stderr=subprocess.STDOUT,timeout=600)
  if p.returncode:break
(r/'SNIPER_BUILD_ISA_EXIT.json').write_text(json.dumps(dict(returncode=p.returncode)))
