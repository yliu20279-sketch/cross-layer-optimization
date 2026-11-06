import pathlib,json,hashlib,subprocess,sys,shutil
R=pathlib.Path(__file__).resolve().parent;B=R.parent;P=B/'lingbot_step4_bitexact_20261029_v4';S=B/'swe_qwen3_legosim_16_layers_20261030_v3';V=B/'swe_qwen3_legosim_16_service_20261030_v1';W=pathlib.Path('/mnt/sdb1/h3240101068/npusim_ramulator2_validation_20260826/workspace')
s=(S/'bridge_full.cpp').read_text();s+="""
#include <map>
static std::map<int,int> peer_rd,peer_wr;
extern "C" __attribute__((visibility("default"))) int um_peer_send(int dst,const void*p,unsigned long long n){TRY
 for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);auto path=InterChiplet::sendSync(rank%4,rank/4,dst%4,dst/4);if(!peer_wr.count(dst))peer_wr[dst]=open(path.c_str(),O_WRONLY);io(peer_wr[dst],(char*)p+off,k,true);auto t=InterChiplet::writeSync(rt->chipCycle(),rank%4,rank/4,dst%4,dst/4,k,0);rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);}return 0;END}
extern "C" __attribute__((visibility("default"))) int um_peer_recv(int src,void*p,unsigned long long n){TRY
 for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);auto path=InterChiplet::receiveSync(src%4,src/4,rank%4,rank/4);if(!peer_rd.count(src))peer_rd[src]=open(path.c_str(),O_RDONLY);io(peer_rd[src],(char*)p+off,k,false);auto t=InterChiplet::readSync(rt->chipCycle(),src%4,src/4,rank%4,rank/4,k,0);rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);}return 0;END}
"""
(R/'bridge.cpp').write_text(s);cmd=json.loads((V/'ACTOR_BUILD_COMMANDS.json').read_text())[0];cmd=[v.replace(str(V/'bridge_actor.cpp'),str(R/'bridge.cpp')).replace(str(V/'libactor.so'),str(R/'libpeer.so')) for v in cmd]
subprocess.run(cmd,check=True,timeout=180)
old=(P/'emulator_build/flash_cpu_combined.cpp').read_text();prefix=old[:old.index('// Own noncausal FlashAttention')];(R/'flash_combined.cpp').write_text(prefix+(R/'flash_head.cpp').read_text()+(R/'rope_head.cpp').read_text());subprocess.run(['g++','-O3','-march=native','-shared','-fPIC','-fopenmp','-ffp-contract=off','-fno-fast-math',str(R/'flash_combined.cpp'),'-o',str(R/'libflash_head.so')],check=True,timeout=180)
shutil.copy2(S/'noc_v3_6.gv',R/'noc_v3_6.gv')
py=B/'lingbot_steps1_2_20261027_v1/venv/bin/python'
def proc(cmd,args,log):return dict(cmd=str(cmd),args=list(map(str,args)),log=log,is_to_stdout=False,clock_rate=1)
phase=[]
for i in range(16):
 phase.append(proc('/usr/bin/env',['SWE_RANK='+str(i),py,R/'worker.py'],'N%02d.log'%i));phase.append(proc(W/'Ramulator2-Chiplet/ramulator2',[i%4,8+i//4,'1.25','--server',W/'Ramulator2-Chiplet/lpddr5_config.yaml',512*2**20,1,R/('ram_N%02d.csv'%i)],'CH%02d.log'%i))
args=[V/'popnet_xy_build/popnet','-A','17','-c','1','-V','3','-B','8','-O','8','-F','4','-L','2000','-T','1000000000000','-r','1','-I','../bench.txt','-R','4','-D','../delayInfo.txt','-G',R/'noc_v3_6.gv','-P']
(R/'config.yml').write_text(json.dumps(dict(phase1=phase,phase2=[proc(py,[R/'phase2.py']+args,'phase2.log')]),indent=2));(R/'BUILD_BINDING.json').write_text(json.dumps(dict(bridge_command=cmd,libpeer_sha256=hashlib.sha256((R/'libpeer.so').read_bytes()).hexdigest(),libflash_sha256=hashlib.sha256((R/'libflash_head.so').read_bytes()).hexdigest(),DRAM_cycle_ns=1.25,CPU_Sniper_included=False),indent=2));print('BUILD_OK')
