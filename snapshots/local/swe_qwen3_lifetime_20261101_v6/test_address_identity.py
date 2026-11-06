import json,subprocess,os,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;S=R/'sniper_isa_candidate';admission=json.loads((R/'EAGER_BINDING_AUDIT_guard.json').read_text());assert admission['state']=='PASS_LIMITED_PORTABLE_ROI_ISA_AND_AVX_REJECTION'
s=(R/'isa_positive.cpp').read_text();needle='std::ofstream(argv[2])<<"PASS_REPRESENTATIVE_CPU_SOFTWARE_AND_LIFETIME_ISA\\n";';assert needle in s
s=s.replace(needle,'std::ofstream(argv[2])<<"PASS_REPRESENTATIVE_CPU_SOFTWARE_AND_LIFETIME_ISA\\n"<<"ADDR "<<(std::uintptr_t)exp_table<<" "<<(std::uintptr_t)silu_table<<" "<<(std::uintptr_t)zero.data()<<" "<<(std::uintptr_t)ones.data()<<" "<<(std::uintptr_t)soft.data()<<"\\n";');(R/'isa_identity.cpp').write_text(s)
cmd=['g++','-O3','-march=nehalem','-mno-avx','-mno-fma','-ffp-contract=off','-fno-fast-math','-std=c++17','-I'+str(S/'include'),'-I'+str(B/'olmoearth_v3_6_integration_20261025_v1/source/NPUSim'),str(R/'isa_identity.cpp'),str(B/'swe_qwen3_norm_20261029_v1/norm_kernel.cpp'),'-o',str(R/'isa_identity')];subprocess.run(cmd,check=True)
addresses=[]
for iteration in [1,2]:
 D=R/('isa_identity_%d'%iteration);D.mkdir(exist_ok=False)
 cmd=['/usr/bin/setarch','x86_64','-R',str(S/'run-sniper'),'-n','4','-c','gainestown','-c',str(B/'swe_qwen3_host_boundary_20261027_v1/cpu_overlay.cfg'),'--roi','--no-cache-warming','-d',str(D),'--',str(R/'isa_identity'),str(R),str(D/'FUNCTIONAL_PASS.txt')]
 with (R/('ISA_IDENTITY_%d.log'%iteration)).open('w') as f:c=subprocess.run(cmd,env=dict(os.environ,GLIBC_TUNABLES=admission['GLIBC_TUNABLES'],LD_BIND_NOW='1'),stdout=f,stderr=subprocess.STDOUT,timeout=180)
 assert c.returncode==0 and (D/'FUNCTIONAL_PASS.txt').exists();line=next(s for s in (D/'FUNCTIONAL_PASS.txt').read_text().splitlines() if s.startswith('ADDR '));addresses.append(list(map(int,line.split()[1:])))
assert addresses[0]==addresses[1],addresses
(R/'CPU_ADDRESS_IDENTITY_PREFLIGHT.json').write_text(json.dumps(dict(state='PASS_LIMITED_ASLR_OFF_REPRESENTATIVE_IDENTITY',addresses=addresses,scope='mmap and vector pointers in two representative actual CPU runs; full-case gate addresses still require equality audit',system_ASLR_setting_changed=False,command='/usr/bin/setarch x86_64 -R',full_steps_1_7=False),indent=2));print('REPRESENTATIVE_ADDRESS_IDENTITY_PASS')
