import json,hashlib,struct,re,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;V=B/'swe_qwen3_legosim_16_service_20261030_v1';OLD=B/'swe_qwen3_legosim_integration_20261030_v1/unified_layers_fifo_v2'
assert json.loads((V/'INDEPENDENT_AUDIT.json').read_text())['state']=='PASS_LIMITED_16_REAL_GATE_HOST_PCIE_HB_NOC_TWO_ROUND'
D=R/'data';D.mkdir(exist_ok=False)
shutil.copy2(V/'HOST_BACKING.json',R/'HOST_BACKING.json');shutil.copy2(V/'data/shards.txt',D/'shards.txt');shutil.copy2(V/'noc_v3_6.gv',R/'noc_v3_6.gv')
for phase in ['prefill','decode']:
 for kind in ['input','gold']:shutil.copy2(OLD/'cpu_data'/(phase+'_'+kind+'.bin'),D/(phase+'_'+kind+'.bin'))
M=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');idx=json.loads((M/'model.safetensors.index.json').read_text())['weight_map'];headers={}
for shard in sorted(set(idx.values())):
 with (M/shard).open('rb') as f:n=struct.unpack('<Q',f.read(8))[0];headers[shard]=(8+n,json.loads(f.read(n)))
params=[];flat=[]
for key in sorted(k for k in idx if k.startswith(('model.layers.0.','model.layers.1.'))):
 shard=idx[key];base,head=headers[shard];v=head[key];assert v['dtype']=='BF16';a,b=v['data_offsets'];off=base+a
 with (M/shard).open('rb') as f:f.seek(off);data=f.read(b-a)
 match=re.search(r'\.experts\.(\d+)\.',key);owner=int(match.group(1))%16 if match else 0
 p=dict(id=len(params),key=key,shape=v['shape'],shard=str(M/shard),offset=off,bytes=b-a,owner=owner,sha256=hashlib.sha256(data).hexdigest());params.append(p)
 N,K=(v['shape'] if len(v['shape'])==2 else [1,v['shape'][0]])
 flat.append('%d %s %d %d %d %d %d'%(p['id'],p['shard'],off,p['bytes'],N,K,owner))
assert len(params)==786
(R/'PARAMETERS.json').write_text(json.dumps(params,indent=2));(D/'parameters.txt').write_text('\n'.join(flat)+'\n')
s=(OLD/'adapter.py').read_text().replace('B=R.parent.parent','B=R.parent').replace("R/'libunified.so'","R/'libfull.so'")
(R/'base_adapter.py').write_text(s)
s=(OLD/'worker.py').read_text();s=s.replace("D=R/'case1';D.mkdir(exist_ok=False)","D=R/('case'+os.environ['SWE_RUN_ROUND']);D.mkdir(exist_ok=True);assert not (D/'FILES.json').exists()")
s=s.replace('from adapter import UnifiedAdapter,UnifiedKV','from full_adapter import FullAdapter,UnifiedKV')
s=s.replace("a=UnifiedAdapter(NativeCodec(B/'swe_qwen3_bf16_functional_v1_20261026/libbf16_codec_bridge.so'),D)","a=FullAdapter(NativeCodec(B/'swe_qwen3_bf16_functional_v1_20261026/libbf16_codec_bridge.so'),D,state)")
assert 'a=FullAdapter(' in s
(R/'worker.py').write_text(s)
s=(V/'bridge_actor.cpp').read_text().replace('#include <memory>','#include <memory>\n#include <algorithm>\n#include <cstdint>')
start=s.index('extern "C" __attribute__((visibility("default"))) int um_recv(');end=s.index('extern "C" __attribute__((visibility("default"))) int um_shutdown(',start)
net='''
static void sendbytes(const void*p,unsigned long long n){for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);auto s=InterChiplet::sendSync(rank%4,rank/4,0,4);if(output_fd<0)output_fd=open(s.c_str(),O_WRONLY);io(output_fd,(char*)p+off,k,true);auto t=InterChiplet::writeSync(rt->chipCycle(),rank%4,rank/4,0,4,k,0);rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);}}
static void recvbytes(void*p,unsigned long long n){for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);auto s=InterChiplet::receiveSync(0,4,rank%4,rank/4);if(input_fd<0)input_fd=open(s.c_str(),O_RDONLY);io(input_fd,(char*)p+off,k,false);auto t=InterChiplet::readSync(rt->chipCycle(),0,4,rank%4,rank/4,k,0);rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);}}
extern "C" __attribute__((visibility("default"))) int um_net_recv(void*p,unsigned long long n){TRY recvbytes(p,n);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_net_send(const void*p,unsigned long long n){TRY sendbytes(p,n);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_recv(void*p,unsigned long long n){TRY recvbytes(p,n);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_send(const void*p,unsigned long long n){TRY static std::uint64_t phase=0;std::uint64_t h[8]={3,phase++,n};sendbytes(h,64);sendbytes(p,n);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_fetch(unsigned long long tag,void*p,unsigned long long n){TRY std::uint64_t h[8]={1,tag,n};sendbytes(h,64);recvbytes(p,n);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_remote(unsigned long long tag,unsigned long long owner,unsigned long long M,unsigned long long N,unsigned long long K,const void*x,void*y){TRY std::uint64_t h[8]={2,tag,M,N,K,2*M*K,2*N*K,owner};sendbytes(h,64);sendbytes(x,2*M*K);recvbytes(y,4*M*N);return 0;END}
'''
s=s[:start]+net+s[end:];(R/'bridge_full.cpp').write_text(s)
cmd=json.loads((V/'ACTOR_BUILD_COMMANDS.json').read_text())[0];cmd=[v.replace(str(V/'bridge_actor.cpp'),str(R/'bridge_full.cpp')).replace(str(V/'libactor.so'),str(R/'libfull.so')) for v in cmd]
W=Path('/mnt/sdb1/h3240101068/npusim_ramulator2_validation_20260826/workspace');I=W/'interchiplet/includes';S=Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim')
commands=[cmd,['g++','-O2','-std=c++17','-I'+str(I),str(R/'gateway.cpp'),'-o',str(R/'gateway')],['g++','-O2','-std=c++17','-I'+str(I),'-I'+str(S/'include'),str(R/'host.cpp'),str(W/'interchiplet_host/lib/libinterchiplet_c.a'),'-pthread','-o',str(R/'host')]]
(R/'BUILD_COMMANDS.json').write_text(json.dumps(commands,indent=2))
for cmd in commands:
 with (R/'BUILD.log').open('a') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
print('FULL_16_LAYER_SERVICE_BUILT',flush=True)
