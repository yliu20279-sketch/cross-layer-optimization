import json,subprocess,sqlite3,os
from pathlib import Path
R=Path(__file__).resolve().parent;S=R/'sniper_isa_candidate';D=R/'isa_probe_usable';D.mkdir(exist_ok=False)
# Names below are present in the installed glibc2.31 loader, unlike the old
# CPUID-bit-style names used for the actual dispatch selectors.
features=['AVX_Usable','FMA_Usable','AVX2_Usable','FMA4_Usable','XSAVEC_Usable','AVX512F_Usable','AVX512DQ_Usable','AVX_Fast_Unaligned_Load','AVX512F','AVX512CD','AVX512DQ','AVX512BW','AVX512ER','AVX512PF','AVX512VL','BMI1','BMI2','LZCNT']
tunable='glibc.cpu.hwcaps='+','.join('-'+x for x in features)
cmd=[str(S/'run-sniper'),'-n','4','-c','gainestown','-c',str(R.parent/'swe_qwen3_host_boundary_20261027_v1/cpu_overlay.cfg'),'--roi','--no-cache-warming','-d',str(D),'--',str(R/'isa_positive'),str(R),str(D/'FUNCTIONAL_PASS.txt')]
with (R/'ISA_USABLE.log').open('w') as f:c=subprocess.run(cmd,env=dict(os.environ,GLIBC_TUNABLES=tunable),stdout=f,stderr=subprocess.STDOUT,timeout=180)
assert c.returncode==0 and (D/'FUNCTIONAL_PASS.txt').exists()
db=sqlite3.connect(str(D/'sim.stats.sqlite3'));rows=db.execute("select n.objectname,n.metricname,v.value from [values] v join names n using(nameid) join prefixes p using(prefixid) where p.prefixname='roi-end' and v.core=0 and n.objectname in ('decoded_isa_nehalem_ok','decoded_isa_nehalem_rejected')").fetchall();db.close()
bad=[dict(name=n,count=v) for obj,n,v in rows if obj=='decoded_isa_nehalem_rejected' and v];assert rows
out=dict(state='PASS_LIMITED_PORTABLE_GLIBC_DISPATCH' if not bad else 'NOT_PROMOTED_GLIBC_DISPATCH',GLIBC_TUNABLES=tunable,rejected=bad,supported=sum(v for o,n,v in rows if o=='decoded_isa_nehalem_ok'),scope='actual representative ROI only; full layers must retain decoded-chip audit',full_steps_1_7=False)
(R/'GLIBC_DISPATCH_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
