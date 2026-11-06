import json,hashlib,shutil,subprocess,os,re
from pathlib import Path
BASE=Path(__file__).resolve().parent;B=BASE.parent;OLD=B/'swe_qwen3_continuous_lowering_20261031_v2';R=B/'swe_qwen3_continuous_lowering_20261031_v3';R.mkdir(exist_ok=False)
for n in json.loads((OLD/'FREEZE.json').read_text()):
 p=R/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(OLD/n,p)
for n in ['BUILD_COMMANDS.json','CPU_BUILD_COMMAND.json','preflight.py','CPU_CONTROLS_ISA.json','cpu_negative_controls.py','audit_raw_when_ready.py','SUPPLEMENTAL_STRICT_GATE.json','safe_collect.py']:
 source=OLD/n
 if not source.exists():source=BASE/n
 shutil.copy2(source,R/n)
for n in ['EXP16_ALL_FP32.bin','SILU_ALL_BF16.bin','oracle_cpu']:os.symlink(str(BASE/n),str(R/n))
s=(R/'bridge_full.cpp').read_text();s=s.replace('static std::ofstream logf;','''static std::ofstream logf,iof;
static void io_stage(unsigned long long n,bool wr,const char*label){if(!n)return;auto start=rt->chipCycle();auto ticks=(n+255)/256;rt->chipCycle()+=ticks;iof<<label<<','<<wr<<','<<n<<','<<start<<','<<rt->chipCycle()<<'\\n';}
''')
s=s.replace('logf.open(std::string(report)+"/program.csv");','iof.open(std::string(report)+"/IO_SRAM_GATES.csv");iof<<"label,write,bytes,start,complete\\n";logf.open(std::string(report)+"/program.csv");')
s=s.replace('rt->store(addr,p,n,"actual_tensor_store");','for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);io_stage(k,false,"HB_store_from_IO_SRAM");rt->store(addr+off,(const char*)p+off,k,"actual_tensor_store");}')
s=s.replace('rt->load(addr,p,n,"actual_tensor_load");','for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);rt->load(addr+off,(char*)p+off,k,"actual_tensor_load");io_stage(k,true,"HB_load_to_IO_SRAM");}')
s=s.replace('auto s=InterChiplet::sendSync(rank%4,rank/4,0,4);','io_stage(k,false,"NoC_send_from_IO_SRAM");auto s=InterChiplet::sendSync(rank%4,rank/4,0,4);')
needle='rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);}}'
recvstart=s.index('static void recvbytes');recv_end=s.index('extern "C"',recvstart);piece=s[recvstart:recv_end];assert needle in piece;piece=piece.replace(needle,'rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);io_stage(k,true,"NoC_receive_to_IO_SRAM");}}');s=s[:recvstart]+piece+s[recv_end:]
old='std::uint64_t h[8]={1,tag,n};sendbytes(h,64);recvbytes(p,n);return 0;'
new='''if(n>32ULL*1024*1024)throw std::runtime_error("BF16 weight slot");std::uint64_t h[8]={1,tag,n};sendbytes(h,64);std::vector<char>b(65536);for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);recvbytes(b.data(),k);io_stage(k,false,"BF16_receive_to_HB");rt->store(off,b.data(),k,"streamed_original_BF16_weight");memcpy((char*)p+off,b.data(),k);}return 0;'''
assert old in s;s=s.replace(old,new)
s+='''
extern "C" __attribute__((visibility("default"))) int um_codec_hb(unsigned long long kind,unsigned long long src,unsigned long long dst,unsigned long long count,void*out){TRY
 if(kind!=1&&kind!=2)throw std::runtime_error("codec kind");auto ib=count*(kind==1?2:4),ob=count*(kind==1?4:2);if(src+ib>536870912ULL||dst+ob>536870912ULL)throw std::runtime_error("codec HB bound");std::uint64_t h[8]={5,kind,ib,ob,count};sendbytes(h,64);std::vector<char>b(65536);
 for(unsigned long long off=0;off<ib;off+=65536){auto k=std::min<unsigned long long>(65536,ib-off);rt->load(src+off,b.data(),k,"BF16_weight_codec_actual_HB_reader");io_stage(k,true,"HB_codec_load_to_IO_SRAM");sendbytes(b.data(),k);}
 for(unsigned long long off=0;off<ob;off+=65536){auto k=std::min<unsigned long long>(65536,ob-off);recvbytes(b.data(),k);io_stage(k,false,"CPU_codec_output_to_HB");rt->store(dst+off,b.data(),k,"CPU_expanded_weight_streamed_HB");memcpy((char*)out+off,b.data(),k);}return 0;END}
'''
s=s.replace('rt->shutdown();logf.flush();','rt->shutdown();logf.flush();iof.flush();');(R/'bridge_full.cpp').write_text(s)
s=(R/'peer.py').read_text();at=s.index('def digest(a):');s=s[:at]+'''def recv_to_hb(n,addr):
 # This large array is a functional mirror of committed HB, not SRAM staging.
 shadow=np.empty(n,dtype='u1')
 for off in range(0,n,65536):
  a=recv(min(65536,n-off));ck(u.um_store(addr+off,a.ctypes.data,a.size));shadow[off:off+a.size]=a
 return shadow
'''+s[at:]
s=s.replace('x=recv(ib);xf=recv(ib*2);ck(u.um_store(320*2**20,xf.ctypes.data,xf.size));ck(u.um_store(32*2**20,x.ctypes.data,ib));','x=recv_to_hb(ib,32*2**20);xf=recv_to_hb(ib*2,320*2**20);')
s=s.replace("wf=recv(wb*2);ck(u.um_store(256*2**20,wf.ctypes.data,wf.size))", "wf=recv_to_hb(wb*2,256*2**20)")
old="raww=np.empty(wb,dtype='u1');ck(u.um_load(0,raww.ctypes.data,wb));assert np.array_equal(raww.view('<u2').astype('<u4')<<16,wf.view('<u4'))"
new="""for off in range(0,wb,65536):
  a=np.empty(min(65536,wb-off),dtype='u1');ck(u.um_load(off,a.ctypes.data,a.size));assert np.array_equal(a.view('<u2').astype('<u4')<<16,wf[off*2:(off+a.size)*2].view('<u4'))"""
assert old in s;s=s.replace(old,new);(R/'peer.py').write_text(s)
s=(R/'integrated_adapter.py').read_text();s=s.replace('self.constants={}',"self.constants={};self.raw_gate=json.loads((self.out.parent/'oracle_cpu/RAW_MATRIX_ORACLE.json').read_text());self.raw_index=0")
s=s.replace('self.um.um_software.argtypes=', 'self.um.um_codec_hb.argtypes=[U,U,U,U,C.c_void_p];self.um.um_software.argtypes=')
s=s.replace("source=np.frombuffer(data,dtype='u1').copy();out=np.empty(outbytes", "assert len(data)+outbytes+196608<=4*2**20, 'generic software staging exceeds SRAM; require streamed HB conversion'\n  source=np.frombuffer(data,dtype='u1').copy();out=np.empty(outbytes")
old="xf=self.codec.decode(xx).numpy();wf=self.codec.decode(ww).numpy();self.ck(self.um.um_store(256*2**20,wf.ctypes.data,wf.nbytes));"
new="""xf=self.codec.decode(xx).numpy();wf=np.empty(tuple(ww.shape),dtype='<f4')
  if p is None:self.ck(self.um.um_store(0,ww.data_ptr(),ww.numel()*2))
  start_codec=int(self.um.um_now());self.ck(self.um.um_codec_hb(1,0,256*2**20,ww.numel(),wf.ctypes.data));self.services.append(dict(id=len(self.services)+1,kind=1,phase=self.phase,layer=self.layer,input_bytes=ww.numel()*2,output_bytes=wf.nbytes,a=ww.numel(),b=0,c=0,start=start_codec,complete=int(self.um.um_now()),input_sha256=hashlib.sha256(self.data(ww)).hexdigest(),output_sha256=hashlib.sha256(wf.tobytes()).hexdigest(),streamed_HB=True,max_staging_bytes=65536));"""
assert old in s;s=s.replace(old,new)
old="node.update(control_ready=ready,prior_service_id=len(getattr(self,'services',[])),prior_compute_job=getattr(self,'job',0));return out"
new="""node.update(control_ready=ready,prior_service_id=len(getattr(self,'services',[])),prior_compute_job=getattr(self,'job',0))
  if label in ['lowered_GEMM_FP32','remote_GEMM_FP32']:
   expected=self.raw_gate[self.raw_index];call=self.generated_calls[-1];same=all(call[k]==expected[k] for k in ['M','N','K']) and node['sha256']==expected['output_sha256'];record=dict(sequence=self.raw_index+1,phase=self.phase,layer=self.layer,M=call['M'],N=call['N'],K=call['K'],node=node['id'],actual_sha256=node['sha256'],expected_sha256=expected['output_sha256'],exact=same,complete=node['ready'])
   with (self.out/'IMMEDIATE_FP32_GATES.jsonl').open('a') as f:f.write(json.dumps(record)+'\\n')
   assert same,('first raw FP32 difference',record);self.raw_index+=1
  return out"""
assert old in s;s=s.replace(old,new);(R/'integrated_adapter.py').write_text(s)
# Rebuild the NPUSim-linked bridge only; target CPU executable/math algorithms stay identical to strict SSE candidate.
commands=json.loads((BASE/'../swe_qwen3_legosim_16_layers_20261030_v3/BUILD_COMMANDS.json').resolve().read_text());cmd=commands[0]
for i,v in enumerate(cmd):
 if re.search(r'/swe_qwen3_legosim_16_layers_20261030_v[123]/',v):cmd[i]=str(R/Path(v).name)
cmd[1:1]=['-ffp-contract=off','-fno-fast-math'];(R/'BRIDGE_BUILD_COMMAND.json').write_text(json.dumps(cmd,indent=2))
with (R/'BRIDGE_BUILD.log').open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
cfg=json.loads((OLD/'unified_full.yml').read_text());(R/'unified_full.yml').write_text(json.dumps(cfg,indent=2).replace(str(OLD),str(R)))
protocol=json.loads((R/'PROTOCOL.json').read_text());protocol.update(previous_attempt=str(OLD),streaming_amendment='64KiB NoC/HB staging; root original BF16 weights actual HB0; weight conversion reads HB0 and streams FP32 toHB256; peer expanded weights streamed before next chunk',SRAM_IO=dict(max_packet_bytes=65536,packet_buffers_bytes=131072,controller_register_reserve=65536,compute_address_end_max=3457024,peak_compute_plus_io=3653632,generic_software_input_output_guard=4*2**20-196608,IO_bank_cost='contiguous32B stripes8banks:ceil(n/256) per read/write; updates real chipCycle',large_python_arrays='functional shadows of committed HB, not SRAM'),immediate_FP32_gate='each of759 matrices SHA checked at publication against unchanged CPU oracle; no output correction')
(R/'PROTOCOL.json').write_text(json.dumps(protocol,indent=2))
for n in ['bridge_full.cpp','peer.py','integrated_adapter.py']:subprocess.run(['/usr/bin/python3','-c','import ast; ast.parse(open(__import__("sys").argv[1]).read())',str(R/n)],check=True) if n.endswith('.py') else None
(R/'STREAM_CANDIDATE_READY.json').write_text(json.dumps(dict(state='BUILT_STREAMED_HB_CANDIDATE',CPU_binary_sha256=hashlib.sha256((R/'host').read_bytes()).hexdigest(),CPU_software_unchanged=True,original_numeric_primitive_header_sha256=hashlib.sha256((R/'sram_matrix.h').read_bytes()).hexdigest()),indent=2));print('STREAM_CANDIDATE_BUILT',flush=True)
