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
s=s.replace('logf.open(std::string(report)', 'bank_report=report;logf.open(std::string(report)');s=s.replace('static std::ofstream logf;','static std::ofstream logf;\nstatic std::string bank_report;');bank=(R/'bank_append.cpp').read_text().replace('static std::string bank_report;','');s+=bank
(R/'bridge.cpp').write_text(s);cmd=json.loads((V/'ACTOR_BUILD_COMMANDS.json').read_text())[0];cmd=[v.replace(str(V/'bridge_actor.cpp'),str(R/'bridge.cpp')).replace(str(V/'libactor.so'),str(R/'libpeer.so')) for v in cmd]
subprocess.run(cmd,check=True,timeout=180)
old=(P/'emulator_build/flash_cpu_combined.cpp').read_text();prefix=old[:old.index('// Own noncausal FlashAttention')];(R/'flash_combined.cpp').write_text(prefix+(R/'flash_head.cpp').read_text()+(R/'rope_head.cpp').read_text());subprocess.run(['g++','-O3','-march=native','-shared','-fPIC','-fopenmp','-ffp-contract=off','-fno-fast-math',str(R/'flash_combined.cpp'),'-o',str(R/'libflash_head.so')],check=True,timeout=180)
# Compile once into this isolated directory; workers only load immutable outputs.
import importlib.util,os
(R/'emulator_build').mkdir(exist_ok=True);os.environ['LINGBOT_TC_BUILD_DIR']=str(R/'emulator_build');sys.path.insert(0,str(P/'upstream'))
spec=importlib.util.spec_from_file_location('isolated_compiler',P/'tc_emulator_simd.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
from tc_profiles import get_profile
emu=mod.TensorCoreEmulator(get_profile('H100','bf16','fp32'))
text=(P/'tc_emulator_simd.py').read_text();a=text.index('        assert self.profile.gpu',text.index('    def _compile(self):'));b=text.index('        self._lib = ctypes.CDLL(lib_path)',a);text=text[:a]+"        lib_path = "+repr(str(R/'emulator_build/_tc_emu_h100_bf16_simd.so'))+"\n"+text[b:];(R/'tc_readonly.py').write_text(text)
text=(P/'target_math_simd.py').read_text().replace('P=pathlib.Path(__file__).resolve().parent',"P=pathlib.Path("+repr(str(P))+")").replace('from tc_emulator_simd import','from tc_readonly import');(R/'math_local.py').write_text(text)
# Regression: compare isolated full GEMM and scalar path on real canonical BF16 data.
import numpy as np
rng=np.random.default_rng(20261031);x=rng.standard_normal((3,32),dtype=np.float32);w=rng.standard_normal((32,16),dtype=np.float32);x.view(np.uint32)[:]&=np.uint32(0xffff0000);w.view(np.uint32)[:]&=np.uint32(0xffff0000)
assert np.array_equal(emu.matmul(x,w).view(np.uint32),emu.matmul_slow(x,w).view(np.uint32))
(R/'BUILD_REGRESSION.json').write_text(json.dumps(dict(status='PASS_ISOLATED_IMMUTABLE_BUILD_GEMM',elements=48,bit_mismatches=0,cache=str(R/'emulator_build'),prior_shared_cache_touched_in_v2=True),indent=2))

shutil.copy2(S/'noc_v3_6.gv',R/'noc_v3_6.gv')
py=B/'lingbot_steps1_2_20261027_v1/venv/bin/python'
def proc(cmd,args,log):return dict(cmd=str(cmd),args=list(map(str,args)),log=log,is_to_stdout=False,clock_rate=1)
phase=[]
for i in range(16):
 phase.append(proc('/usr/bin/env',['SWE_RANK='+str(i),py,R/'worker.py'],'N%02d.log'%i));phase.append(proc(W/'Ramulator2-Chiplet/ramulator2',[i%4,8+i//4,'1.25','--server',W/'Ramulator2-Chiplet/lpddr5_config.yaml',512*2**20,1,R/('ram_N%02d.csv'%i)],'CH%02d.log'%i))
args=[V/'popnet_xy_build/popnet','-A','17','-c','1','-V','3','-B','8','-O','8','-F','4','-L','2000','-T','1000000000000','-r','1','-I','../bench.txt','-R','4','-D','../delayInfo.txt','-G',R/'noc_v3_6.gv','-P']
(R/'config.yml').write_text(json.dumps(dict(phase1=phase,phase2=[proc(py,[R/'phase2.py']+args,'phase2.log')]),indent=2));(R/'BUILD_BINDING.json').write_text(json.dumps(dict(bridge_command=cmd,libpeer_sha256=hashlib.sha256((R/'libpeer.so').read_bytes()).hexdigest(),libflash_sha256=hashlib.sha256((R/'libflash_head.so').read_bytes()).hexdigest(),DRAM_cycle_ns=1.25,CPU_Sniper_included=False),indent=2));print('BUILD_OK')
