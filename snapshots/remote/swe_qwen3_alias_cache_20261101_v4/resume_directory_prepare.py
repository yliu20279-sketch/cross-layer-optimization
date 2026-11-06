import json,shutil,subprocess,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;S=R/'sniper_drain_candidate';C=S/'common';P=C/'core/memory_subsystem';M=P/'parametric_dram_directory_msi';T=P/'pr_l1_pr_l2_dram_directory_msi'
s=(R/'prepare_directory_drain.py').read_text();a=s.index("p=M/'memory_manager.h';s=p.read_text();needle=")
exec(compile(s[a:],str(R/'prepare_directory_drain.py'),'exec'))
