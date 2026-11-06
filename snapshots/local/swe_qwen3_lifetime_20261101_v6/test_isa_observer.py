import json,subprocess,sqlite3,os
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;S=R/'sniper_isa_candidate';assert json.loads((R/'ISA_OBSERVER_BUILD_EXIT.json').read_text())['state']=='BUILD_ONLY_NOT_ISA_PASS'
common=['g++','-O3','-march=nehalem','-mno-avx','-mno-fma','-ffp-contract=off','-fno-fast-math','-std=c++17','-I'+str(S/'include'),'-I'+str(B/'olmoearth_v3_6_integration_20261025_v1/source/NPUSim')]
results=[]
for mode in ['positive','negative']:
 executable=R/('isa_'+mode);cmd=common+[str(R/('isa_'+mode+'.cpp'))]
 if mode=='positive':cmd+=[str(B/'swe_qwen3_norm_20261029_v1/norm_kernel.cpp')]
 subprocess.run(cmd+['-o',str(executable)],check=True)
 D=R/('isa_probe_'+mode);D.mkdir(exist_ok=False);argv=[str(executable)]+([str(R)] if mode=='positive' else [])+[str(D/'FUNCTIONAL_PASS.txt')]
 cmd=[str(S/'run-sniper'),'-n','4','-c','gainestown','-c',str(B/'swe_qwen3_host_boundary_20261027_v1/cpu_overlay.cfg'),'--roi','--no-cache-warming','-d',str(D),'--']+argv
 env=dict(os.environ,GLIBC_TUNABLES='glibc.cpu.hwcaps=-AVX512F,-AVX512VL,-AVX2,-AVX,-FMA,-FMA4')
 with (R/('ISA_'+mode.upper()+'.log')).open('w') as f:c=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=180)
 assert c.returncode==0 and (D/'FUNCTIONAL_PASS.txt').exists(),mode
 db=sqlite3.connect(str(D/'sim.stats.sqlite3'));rows=db.execute("select n.objectname,n.metricname,v.value from [values] v join names n using(nameid) join prefixes p using(prefixid) where p.prefixname='roi-end' and v.core=0 and n.objectname in ('decoded_isa_nehalem_ok','decoded_isa_nehalem_rejected')").fetchall();db.close()
 assert rows;bad=[dict(name=n,count=v) for obj,n,v in rows if obj=='decoded_isa_nehalem_rejected' and v];ok=sum(v for obj,n,v in rows if obj=='decoded_isa_nehalem_ok')
 results.append(dict(mode=mode,supported_decoded_occurrences=ok,rejected=bad))
out=dict(state='PASS_LIMITED_XED_NEHALEM_OBSERVER_CONTROLS' if not results[0]['rejected'] and results[1]['rejected'] else 'NOT_PROMOTED_ISA_OBSERVER',results=results,scope='representative actual CPU software paths including libraries; negative AVX must be detected; complete layers still require final ISA audit',full_steps_1_7=False)
(R/'ISA_OBSERVER_CONTROLS.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
