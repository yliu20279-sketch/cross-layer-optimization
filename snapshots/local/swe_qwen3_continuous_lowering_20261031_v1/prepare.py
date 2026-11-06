import json,hashlib,shutil,subprocess,re
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;OLD=B/'swe_qwen3_legosim_16_layers_20261030_v3'
assert not (R/'host.cpp').exists(),'isolated one-time prepare'
names=['data','base_adapter.py','full_adapter.py','worker.py','peer.py','bridge_full.cpp','host.cpp','gateway.cpp','PARAMETERS.json','HOST_BACKING.json','EXPECTED.json','noc_v3_6.gv','CLOCK_BINDING.json','CLOCK_AMENDMENT.json','check_case.py','audit_clock.py']
for n in names:
 if (OLD/n).is_dir():shutil.copytree(OLD/n,R/n)
 else:shutil.copy2(OLD/n,R/n)
s=(R/'bridge_full.cpp').read_text();s+='''
#include "sram_matrix.h"
extern "C" __attribute__((visibility("default"))) int um_matrix(unsigned long long x,unsigned long long w,unsigned long long y,unsigned long long M,unsigned long long N,unsigned long long K,unsigned long long job,const char*d){TRY SramMatrix k(*rt);k.run(x,w,y,M,N,K,job,d);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_binary(unsigned long long x,unsigned long long w,unsigned long long y,unsigned long long n,unsigned long long mul,unsigned long long job,const char*d){TRY SramMatrix k(*rt);k.binary(x,w,y,n,mul,job,d);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_software(unsigned long long kind,const void*x,unsigned long long ib,void*y,unsigned long long ob,unsigned long long a,unsigned long long b,unsigned long long c){TRY std::uint64_t h[8]={5,kind,ib,ob,a,b,c};sendbytes(h,64);sendbytes(x,ib);recvbytes(y,ob);return 0;END}
''';(R/'bridge_full.cpp').write_text(s)
s=(R/'worker.py').read_text().replace('from full_adapter import FullAdapter,UnifiedKV','from integrated_adapter import FullAdapter,UnifiedKV');(R/'worker.py').write_text(s)
s=(R/'host.cpp').read_text().replace('struct Param {','#include "cpu_services.h"\nstruct Param {')
s=s.replace('std::uint64_t jobs=0,fetches=0;SimRoiStart();','''auto map_table=[&](const std::string&name,std::uint64_t expected){int fd=open((root+"/../"+name).c_str(),O_RDONLY);struct stat st;if(fd<0||fstat(fd,&st)||(std::uint64_t)st.st_size!=expected)throw std::runtime_error("math table size");void*p=mmap(nullptr,expected,PROT_READ,MAP_PRIVATE,fd,0);close(fd);if(p==MAP_FAILED)throw std::runtime_error("math mmap");return p;};
 exp_table=(const float*)map_table("EXP16_ALL_FP32.bin",1ULL<<34);silu_table=(const std::uint16_t*)map_table("SILU_ALL_BF16.bin",131072);
 if(total+(1ULL<<34)+131072+(512ULL<<20)>128ULL*1024*1024*1024)throw std::runtime_error("host with software data capacity");
 std::ofstream service_log(out+"/CPU_SERVICE_COMPLETIONS.jsonl");std::uint64_t software_jobs=0,jobs=0,fetches=0;SimRoiStart();''')
s=s.replace('auto id=h[1]&0xffffffffULL;', '''if(h[0]==5){if(h[2]>(128ULL<<20)||h[3]>(128ULL<<20))throw std::runtime_error("software buffer bound");std::vector<char>in(h[2]),outbuf(h[3]);receive(in.data(),in.size());service(h,in,outbuf);send(outbuf.data(),outbuf.size());software_jobs++;service_log<<"{\\"kind\\":"<<h[1]<<",\\"input_bytes\\":"<<h[2]<<",\\"output_bytes\\":"<<h[3]<<"}\\n";continue;}
   auto id=h[1]&0xffffffffULL;''')
s=s.replace('receive(x.data(),x.size());send(x.data(),x.size());send(w,v.bytes);receive(y.data(),y.size());send(y.data(),y.size());jobs++;','''receive(x.data(),x.size());std::vector<float>xf(M*K),wf(N*K);
    for(std::uint64_t i=0;i<M*K;i++){std::uint16_t bits;memcpy(&bits,x.data()+2*i,2);xf[i]=dec(bits);}for(std::uint64_t i=0;i<N*K;i++){std::uint16_t bits;memcpy(&bits,w+2*i,2);wf[i]=dec(bits);}
    send(x.data(),x.size());send(xf.data(),xf.size()*4);send(w,v.bytes);send(wf.data(),wf.size()*4);receive(y.data(),y.size());send(y.data(),y.size());jobs++;''')
s=s.replace('SimRoiEnd();std::ofstream','SimRoiEnd();service_log.flush();std::ofstream');(R/'host.cpp').write_text(s)
s=(R/'gateway.cpp').read_text();s=s.replace('if(h[0]==1){','if(h[0]==5){w.forward(0,48,h[2]);w.forward(48,0,h[3]);}\n   else if(h[0]==1){')
s=s.replace('w.forward(48,owner,h[5]);w.forward(48,owner,h[6]);','w.forward(48,owner,h[5]);w.forward(48,owner,2*h[5]);w.forward(48,owner,h[6]);w.forward(48,owner,2*h[6]);');(R/'gateway.cpp').write_text(s)
s=(R/'peer.py').read_text();s=s.replace("u.um_init.argtypes=[C.c_char_p];", "u.um_matrix.argtypes=[U,U,U,U,U,U,U,C.c_char_p];u.um_init.argtypes=[C.c_char_p];")
s=s.replace('x=recv(ib);ck(u.um_store(32*2**20,x.ctypes.data,ib));wh=hashlib.sha256()', 'x=recv(ib);xf=recv(ib*2);ck(u.um_store(320*2**20,xf.ctypes.data,xf.size));ck(u.um_store(32*2**20,x.ctypes.data,ib));wh=hashlib.sha256()')
start=s.index(" assert wh.hexdigest()==p['sha256']");end=s.index(" ck(u.um_net_send",start)
s=s[:start]+''' assert wh.hexdigest()==p['sha256'];wf=recv(wb*2);ck(u.um_store(256*2**20,wf.ctypes.data,wf.size))
 assert np.array_equal(x.view('<u2').astype('<u4')<<16,xf.view('<u4'))
 raww=np.empty(wb,dtype='u1');ck(u.um_load(0,raww.ctypes.data,wb));assert np.array_equal(raww.view('<u2').astype('<u4')<<16,wf.view('<u4'))
 actual_x=x;rh=wh;ck(u.um_matrix(320*2**20,256*2**20,324*2**20,M,N,K,tag>>32,str(out).encode()));compute=int(u.um_now());last=compute
 back=np.empty((M,N),dtype='<f4');ck(u.um_load(324*2**20,back.ctypes.data,back.nbytes))
''' +s[end:];(R/'peer.py').write_text(s)
commands=json.loads((OLD/'BUILD_COMMANDS.json').read_text())
for cmd in commands:
 for i,v in enumerate(cmd):
  if re.search(r'/swe_qwen3_legosim_16_layers_20261030_v[123]/',v):cmd[i]=str(R/Path(v).name)
 cmd[1:1]=['-ffp-contract=off','-fno-fast-math']
 if cmd[-1].endswith('/host'):
  cmd.insert(1,'-I'+str(B/'olmoearth_v3_6_integration_20261025_v1/source/NPUSim'));cmd.insert(-2,str(B/'swe_qwen3_norm_20261029_v1/norm_kernel.cpp'))
(R/'BUILD_COMMANDS.json').write_text(json.dumps(commands,indent=2))
for c in commands:
 with (R/'BUILD.log').open('a') as f:subprocess.run(c,stdout=f,stderr=subprocess.STDOUT,check=True)
cfg=json.loads((OLD/'unified_full.yml').read_text());cfg=json.loads(json.dumps(cfg).replace(str(OLD),str(R)));(R/'unified_full.yml').write_text(json.dumps(cfg,indent=2))
print('FULL_INTEGRATION_BUILT',flush=True)
