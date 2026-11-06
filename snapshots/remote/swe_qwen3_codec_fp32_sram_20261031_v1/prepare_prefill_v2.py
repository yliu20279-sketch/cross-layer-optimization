import json,hashlib,shutil,subprocess
from pathlib import Path
import numpy as np,ctypes as C
OLD=Path(__file__).resolve().parent;B=OLD.parent;R=B/'swe_qwen3_codec_prefill_sram_20261031_v2';R.mkdir(exist_ok=False)
for n in ['host.cpp','gateway.cpp','bridge_actor.cpp','actor.py','sram_kernel.h','run.py','phase2_gate.py','freeze_launch.py','data','CASES.json','HOST_BACKING.json']:
 p=OLD/n
 if p.is_dir():shutil.copytree(p,R/n)
 else:shutil.copy2(p,R/n)
ref=B/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1';routes=np.fromfile(ref/'prefill_L0_route_IDs.bin',dtype='<i8').reshape(19,8);tokens=np.where(routes==16)[0];assert tokens.tolist()==[0,2,11,14,16,18]
xb=np.fromfile(ref/'prefill_L0_post_attention_norm.bin',dtype='<u2').reshape(19,2048)[tokens].copy();xp=R/'data/prefill_expert16_M6_x.bin';xp.write_bytes(xb.tobytes())
parts=(R/'data/plan.txt').read_text().splitlines()[0].split();parts[2]='6';parts[6]=str(xp);parts[7]=str(R/'data/prefill_expert16_M6_gold.bin');(R/'data/plan.txt').write_text(' '.join(parts)+'\n')
with open(parts[3],'rb') as f:f.seek(int(parts[4]));w=np.frombuffer(f.read(int(parts[5])),dtype='<u2').copy()
lib=C.CDLL(str(B/'swe_qwen3_step3_four_gates_20261028_v1/libsource_gemm_v2.so'));lib.source_gemm.argtypes=[C.c_void_p]*3+[C.c_int]*3;y=np.empty((6,768),dtype='<f4');assert lib.source_gemm(xb.ctypes.data,w.ctypes.data,y.ctypes.data,6,768,2048)==0
bits=y.view('<u4');rounded=((bits+0x7fff+((bits>>16)&1))>>16).astype('<u2');Path(parts[7]).write_bytes(rounded.tobytes());(R/'data/source_FP32.bin').write_bytes(y.tobytes())
protocol=dict(state='PREREGISTERED_REAL_PREFILL_BATCH',expert=16,M=6,N=768,K=2048,tokens=tokens.tolist(),input_source=str(ref/'prefill_L0_post_attention_norm.bin'),input_source_sha256=hashlib.sha256((ref/'prefill_L0_post_attention_norm.bin').read_bytes()).hexdigest(),original_BF16=True,host_GiB=128,HB_GiB=8,active_NPU=0,active_HB_MiB=512,CPU_conversion='actual Sniper ROI',batch_order='CPU source odd/even K blocks 768/768/512; no tolerance relaxation',SRAM='8 banks 4MiB; stripe32 one shared port explicit research point',GPU_differences='retained',full_steps_1_7=False)
(R/'PROTOCOL.json').write_text(json.dumps(protocol,indent=2))
s=(R/'host.cpp').read_text().replace('x.size()!=4096','x.size()!=24576').replace('gold.size()!=1536','gold.size()!=9216').replace('xf(2048)','xf(12288)').replace('y(768)','y(4608)').replace('bits(768)','bits(4608)').replace('i<2048','i<12288').replace('token,2048,768,bytes,4096','token,2048,768,bytes,24576').replace('send(x.data(),4096)','send(x.data(),24576)').replace('send(xf.data(),8192)','send(xf.data(),49152)').replace('i<768','i<4608').replace('gold.data(),1536','gold.data(),9216').replace('y.data(),3072','y.data(),18432').replace('bits.data(),1536','bits.data(),9216').replace('xf.data(),8192','xf.data(),49152').replace('(2048+bytes/2)','(12288+bytes/2)').replace('encoded_elements\\\":768','encoded_elements\\\":4608')
(R/'host.cpp').write_text(s)
s=(R/'gateway.cpp').read_text().replace('result(h[4]*4)','result(h[4]*h[2]*4)');(R/'gateway.cpp').write_text(s)
s=(R/'actor.py').read_text().replace('3145728,4096,0x00040003','3145728,24576,0x00040003').replace('y=np.empty(N,','y=np.empty(6*N,');(R/'actor.py').write_text(s)
s=(R/'sram_kernel.h').read_text();start=s.index('   for(int nn=0;nn<64;nn++){');end=s.index('\n  access({{Y,N*4ULL}}',start)
body='''   for(int m=0;m<6;m++)for(int sub=0;sub<64;sub+=16){
    auto row_start=rt.chipCycle();const std::uint64_t T=A+128;
    bool first=true;
    for(int k0=0;k0<K;k0+=768){
     access({{A,64}},true);std::memset(mem.data()+A,0,64);
     int end=std::min(K,k0+768);
     for(int kk=k0;kk<end;kk+=2)for(int parity=1;parity>=0;parity--){
      int k=kk+parity;if(k>=end)continue;
      std::vector<std::pair<std::uint64_t,std::uint64_t>> req{{X+(m*K+k)*4ULL,4},{A,64}};
      for(int lane=0;lane<16;lane++)req.push_back({W+((sub+lane)*K+k)*4ULL,4});
      access(req,false);last_reader=rt.chipCycle();float p[16],a[16];
      for(int lane=0;lane<16;lane++){p[lane]=get(X+(m*K+k)*4ULL)*get(W+((sub+lane)*K+k)*4ULL);a[lane]=get(A+lane*4);}
      op(16,false,1);mul_ops+=16;for(int lane=0;lane<16;lane++)a[lane]=a[lane]+p[lane];op(16,false,2);add_ops+=16;
      access({{A,64}},true);for(int lane=0;lane<16;lane++)put(A+lane*4,a[lane]);
     }
     access({{A,64}},false);float acc[16];for(int lane=0;lane<16;lane++)acc[lane]=get(A+lane*4);
     if(!first){access({{T,64}},false);for(int lane=0;lane<16;lane++)acc[lane]=get(T+lane*4)+acc[lane];op(16,false,2);add_ops+=16;}
     access({{T,64}},true);for(int lane=0;lane<16;lane++)put(T+lane*4,acc[lane]);first=false;
    }
    access({{T,64}},false);float result[16];for(int lane=0;lane<16;lane++)result[lane]=get(T+lane*4);
    access({{Y+(m*N+n0+sub)*4ULL,64}},true);for(int lane=0;lane<16;lane++)put(Y+(m*N+n0+sub+lane)*4ULL,result[lane]);
    rows<<(m*N+n0+sub)<<','<<row_start<<','<<rt.chipCycle()<<','<<version<<','<<last_reader<<'\\n';
   }
  }'''
s=s[:start]+body+s[end:];s=s.replace('X=0,W=8192','X=0,W=65536').replace('K*4,"FP32_X','6*K*4,"FP32_X').replace('{{X,K*4ULL}}','{{X,6*K*4ULL}}').replace('{{Y,N*4ULL}}','{{Y,6*N*4ULL}}').replace('mem.data()+Y,N*4ULL','mem.data()+Y,6*N*4ULL');(R/'sram_kernel.h').write_text(s)
commands=json.loads((OLD/'BUILD_COMMANDS.json').read_text());commands=[[v.replace(str(OLD),str(R)) for v in c] for c in commands];(R/'BUILD_COMMANDS.json').write_text(json.dumps(commands,indent=2))
for c in commands:
 with (R/'BUILD.log').open('a') as f:subprocess.run(c,stdout=f,stderr=subprocess.STDOUT,check=True)
cfg=json.loads((OLD/'unified.yml').read_text());(R/'unified.yml').write_text(json.dumps(cfg).replace(str(OLD),str(R)))
for n in ['sniper','case1','case2']:(R/n).mkdir()
names=['host.cpp','host','gateway.cpp','gateway','bridge_actor.cpp','libactor.so','actor.py','sram_kernel.h','PROTOCOL.json','unified.yml','phase2_gate.py','data/plan.txt','data/shards.txt','data/source_FP32.bin','data/prefill_expert16_M6_x.bin','data/prefill_expert16_M6_gold.bin']
(R/'FREEZE.json').write_text(json.dumps({n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in names},indent=2))
subprocess.run(['/usr/bin/python3',str(R/'freeze_launch.py')],check=True)
