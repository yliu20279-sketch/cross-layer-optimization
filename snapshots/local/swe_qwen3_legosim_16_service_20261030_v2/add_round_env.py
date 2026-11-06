from pathlib import Path
import shutil,subprocess
R=Path(__file__).resolve().parent;p=R/'interchiplet.cpp';s=p.read_text();assert 'SWE_RUN_ROUND' not in s
shutil.copy2(p,R/'interchiplet_before_round_env.cpp')
s=s.replace('swe_domain::reset();','setenv("SWE_RUN_ROUND", std::to_string(__round).c_str(), 1);\n    swe_domain::reset();',1);p.write_text(s)
with (R/'BUILD_ROUND_ENV.log').open('w') as f:subprocess.run(['cmake','--build',str(R/'build'),'-j','4'],stdout=f,stderr=subprocess.STDOUT,check=True)
