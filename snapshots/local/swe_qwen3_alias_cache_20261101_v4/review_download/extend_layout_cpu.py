import json,hashlib,subprocess,ast
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent
p=R/'cpu_services.h';s=p.read_text();needle=' else throw std::runtime_error("unknown CPU software service");';assert needle in s
s=s.replace(needle,''' else if(kind==22){if(c<1||c>8||in.size()!=a*b+(1+2*c)*8||!b||out.size()%b)throw std::runtime_error("strided descriptor size");std::int64_t meta[17];memcpy(meta,in.data()+a*b,(1+2*c)*8);U count=1;for(U d=0;d<c;d++){if(meta[1+d]<1||meta[1+c+d]<0)throw std::runtime_error("strided shape");count*=meta[1+d];}if(count*b!=out.size())throw std::runtime_error("strided output size");for(U i=0;i<count;i++){U rem=i;std::int64_t idx=meta[0];for(int d=int(c)-1;d>=0;d--){idx+=(rem%meta[1+d])*meta[1+c+d];rem/=meta[1+d];}if(idx<0||U(idx)>=a)throw std::runtime_error("strided bounds");memcpy(out.data()+i*b,in.data()+idx*b,b);}}
'''+needle);p.write_text(s)
p=R/'integrated_adapter.py';s=p.read_text();start=s.index("   index=np.full(tuple(t.shape)");end=s.index(";actual=torch.from_numpy(out)",start)
s=s[:start]+'''   sizes=list(t.shape);strides=list(t.stride());maximum=delta//size+sum((n-1)*stride for n,stride in zip(sizes,strides))
   if t.numel()==0 or maximum>=base.numel():continue
   meta=np.asarray([delta//size]+sizes+strides,dtype='<i8');raw=np.empty(node['bytes'],dtype='u1');self.ck(self.um.um_load(node['offset'],raw.ctypes.data,raw.size));out=self.software(22,raw.tobytes()+meta.tobytes(),t.numel()*size,base.numel(),size,t.ndim)'''+s[end:];ast.parse(s);p.write_text(s)
meta=json.loads((R/'ALIAS_METHOD.json').read_text());meta.update(strided_address_generation='actual CPU integer division/multiply/strides, service22; no precomputed index array supplied',integrated_adapter_sha256=hashlib.sha256(p.read_bytes()).hexdigest());(R/'ALIAS_METHOD.json').write_text(json.dumps(meta,indent=2))
PY=B/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python';subprocess.run([str(PY),str(R/'preflight.py')],check=True)
worker=R/'control_replay.py';s=worker.read_text().replace("D=R/'control_replay'","D=R/'control_replay_v2'");worker.write_text(s)
with (R/'CONTROL_REPLAY_V2.log').open('w') as f:p=subprocess.Popen(['/usr/bin/timeout','1800',str(PY),str(worker)],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'CONTROL_REPLAY_V2_PID.json').write_text(json.dumps(dict(pid=p.pid,bound_seconds=1800,target_native_runs=0,GPU_runs=0)));print('ALIAS_CPU_STRIDE_REPLAY_STARTED',p.pid)
