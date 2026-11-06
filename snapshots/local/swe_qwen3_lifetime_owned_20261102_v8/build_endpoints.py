import json,shutil,subprocess,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;V=R.parent/'swe_qwen3_lifetime_20261101_v6'
shutil.copy2(V/'sram_matrix.h',R/'sram_matrix.h')
s=(V/'bridge_full.cpp').read_text()
s+='''
extern "C" __attribute__((visibility("default"))) int um_finalize(){TRY
 std::uint64_t h[8]={6,0x51424d4bULL},ack[8];sendbytes(h,64);recvbytes(ack,64);
 if(ack[0]!=6||ack[1]!=h[1]||ack[2]||ack[3]||ack[4]||ack[5]!=(208ULL<<20)||ack[6]||ack[7])throw std::runtime_error("final ownership acknowledgement");
 return 0;END}
'''
(R/'bridge_full.cpp').write_text(s)
commands={}
for name in ['CPU','BRIDGE']:
 cmd=json.loads((V/(name+'_BUILD_COMMAND.json')).read_text())
 cmd=[x.replace(str(V),str(R)).replace(str(R.parent/'swe_qwen3_continuous_lowering_20261031_v3'),str(R)) for x in cmd]
 commands[name]=cmd
inc='/mnt/sdb1/h3240101068/npusim_ramulator2_validation_20260826/workspace/interchiplet/includes'
commands['GATEWAY']=['g++','-std=c++17','-O2','-I'+inc,str(R/'gateway.cpp'),'-o',str(R/'gateway')]
for name,cmd in commands.items():
 (R/(name+'_BUILD_COMMAND.json')).write_text(json.dumps(cmd,indent=2))
 with (R/(name+'_BUILD.log')).open('w') as f:subprocess.run(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=600)
out=dict(state='BUILD_ONLY_NOT_ENDPOINT_VALIDATION',binaries={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in ['host','gateway','libfull.so']},native_runs=0,full_steps_1_7=False)
(R/'ENDPOINT_BUILD.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
