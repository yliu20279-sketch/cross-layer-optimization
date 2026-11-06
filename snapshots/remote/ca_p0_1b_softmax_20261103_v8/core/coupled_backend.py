"""Synchronous functional RPC to one live NPUSim/Ramulator/PopNet state.

Host IPC/codec/software CPU and PCIe costs remain explicitly uncertified.
No fixture outputs or independent timing replay enter this interface.
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time
import numpy as np
from .common import require
from .native_payload import NativePayload

MAGIC=0x5035434f55504c45


class LiveBackend:
    def __init__(self,binary,expected_sha256,out,ram_config,controls='project_dynamic',timeout=600):
        binary=Path(binary);out=Path(out)
        require(binary.is_file() and hashlib.sha256(binary.read_bytes()).hexdigest()==expected_sha256,'coupled binary identity changed')
        require(not out.exists() and controls in ('off','project_dynamic'),'invalid/new output required')
        out.mkdir(parents=True);(out/'empty.trace').write_bytes(b'')
        self.out=out;self.live={};self.clock=0;self.events=[];self.closed=False
        self.err=(out/'backend.stderr').open('wb')
        cmd=['timeout','--signal=TERM',str(timeout),str(binary),str(out),str(ram_config),controls]
        env={'PATH':'/usr/bin:/bin','POPNET_COUPLED':'1','POPNET_STATS_DIR':str(out),
             'POPNET_STATS_WINDOW_CYCLES':'100000'}
        self.process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err,env=env,cwd=out)
        try:
            hello=struct.unpack('<8Q',self._read(64));require(hello[0]==MAGIC,'backend handshake differs')
        except Exception:
            self.abort();raise
        (out/'LAUNCH.json').write_text(json.dumps({'command':cmd,'environment':env,'binary_sha256':expected_sha256,
            'scope':'bounded coupled functional check','cpu_pcie_costs_verified':False,'formal_performance':False},indent=2))

    def _read(self,n):
        chunks=[]
        while n:
            data=self.process.stdout.read(n)
            require(bool(data),'coupled backend terminated; inspect preserved backend.stderr')
            chunks.append(data);n-=len(data)
        return b''.join(chunks)

    def rpc(self,op,*args,payload=None):
        require(not self.closed and 0<op<=11 and len(args)<=7,'invalid live RPC')
        fields=[op]+list(args);fields += [0]*(8-len(fields))
        begin=self.clock
        self.process.stdin.write(struct.pack('<8Q',*fields))
        if payload is not None:self.process.stdin.write(payload)
        self.process.stdin.flush();answer=struct.unpack('<8Q',self._read(64))
        require(answer[0]==MAGIC,'corrupt live RPC response')
        if answer[1]:raise RuntimeError(self._read(answer[2]).decode('utf-8','replace'))
        self.clock=answer[2] if op in (2,3,8) else answer[7]
        self.events.append({'sequence':len(self.events),'opcode':op,'arguments':list(args),
             'start':begin,'complete':self.clock,'reply':list(answer),
             'host_payload_sha256':None if payload is None else hashlib.sha256(payload).hexdigest()})
        return answer

    def alloc(self,rank,size,role=0):
        require(isinstance(rank,int) and 0<=rank<16 and isinstance(size,int) and 0<size<=512*1024**2,'invalid HB extent')
        require(role in (0,1,2),'invalid object role')
        answer=self.rpc(1,rank,size,role);handle=answer[2]
        require(handle not in self.live,'reused live handle');self.live[handle]=(rank,size,role)
        return handle

    def put(self,handle,data,offset=0):
        require(handle in self.live and data and offset>=0 and offset+len(data)<=self.live[handle][1],'write exceeds live extent')
        self.rpc(2,handle,offset,len(data),payload=data)

    def get(self,handle,size=None,offset=0):
        require(handle in self.live,'stale handle')
        size=self.live[handle][1]-offset if size is None else size
        require(size>0 and offset>=0 and offset+size<=self.live[handle][1],'read exceeds live extent')
        answer=self.rpc(3,handle,offset,size);require(answer[3]==size,'read reply size differs')
        return self._read(size)

    def free(self,handle):
        require(handle in self.live,'double/stale release');self.rpc(4,handle);del self.live[handle]

    def stage(self,rank,data,role=0):
        handle=self.alloc(rank,len(data),role);self.put(handle,data);return handle

    def layout(self):
        answer=self.rpc(11);require(answer[3]==answer[2]*32,'layout reply size differs')
        raw=self._read(answer[3]) if answer[3] else b''
        rows=np.frombuffer(raw,dtype='<u8').reshape(-1,4)
        return rows.copy(),answer[4]

    def install_layout(self,rows,expected_generation,budget_percent=10):
        rows=np.asarray(rows,dtype='<u8')
        require(rows.ndim==2 and rows.shape[1]==3 and len(rows)>0,'mapping triples required')
        return self.rpc(10,len(rows),budget_percent,expected_generation,payload=rows.tobytes())

    def close(self):
        require(not self.live,'cannot close with live tensor/KV objects')
        self.rpc(8);self.closed=True;self.process.stdin.close()
        code=self.process.wait(timeout=30);self.err.close();require(code==0,'coupled backend failed at shutdown')
        return json.loads((self.out/'BACKEND_SUMMARY.json').read_text())

    def abort(self):
        if self.process.poll() is None:self.process.terminate()
        self.process.wait(timeout=30);self.err.close();self.closed=True


class CoupledPayload:
    scope='live NPUSim numerical SRAM primitive + actual DRAM/NoC callbacks; host software costs unverified'
    def __init__(self,backend,codec_library,codec_sha256):
        self.backend=backend;self.codec=NativePayload(codec_library,codec_sha256)
        self.partition=0;self.label='';self.calls=[];self.software=[];self.publications=[];self.weight_cache={}

    def select_partition(self,partition,label=''):
        require(isinstance(partition,int) and 0<=partition<16,'invalid execution partition')
        self.partition=partition;self.label=label

    def decode(self,data,dtype):return self.codec.decode(data,dtype)
    def encode(self,data,dtype):return self.codec.encode(data,dtype)

    def commit(self,data,label='software_commit'):
        """Publish actual bytes only after a real HB write/read completion."""
        begin=self.backend.clock;handle=self.backend.stage(self.partition,data)
        result=self.backend.get(handle);self.backend.free(handle)
        require(result==data,'actual HB commit differs')
        self.publications.append({'handle':handle,'partition':self.partition,'bytes':len(data),'label':label,
            'start':begin,'complete':self.backend.clock,'payload_sha256':hashlib.sha256(result).hexdigest()})
        return result

    def software_op(self,label,inputs,fn):
        begin=self.backend.clock;actual=[self.commit(data,label+'_input') for data in inputs]
        start=time.perf_counter_ns();result=fn(actual);elapsed=time.perf_counter_ns()-start
        require(isinstance(result,bytes) and bool(result),'software service returned invalid bytes')
        result=self.commit(result,label+'_output')
        self.software.append({'label':label,'partition':self.partition,'start_target_ns':begin,
             'complete_target_ns':self.backend.clock,'input_bytes':sum(map(len,inputs)),'output_bytes':len(result),
             'host_wall_ns':elapsed,'target_cpu_cost_verified':False,'PCIe_cost_verified':False})
        return result

    def _f32_binary(self,a,b,mul=False):
        require(a and len(a)==len(b) and len(a)%4==0,'FP32 vector shape differs')
        backend=self.backend;handles=[]
        try:
            ah=backend.stage(self.partition,a);handles.append(ah)
            bh=backend.stage(self.partition,b);handles.append(bh)
            ch=backend.alloc(self.partition,len(a));handles.append(ch)
            backend.rpc(6,ah,bh,ch,len(a)//4,int(mul))
            return backend.get(ch)
        finally:
            for handle in reversed(handles):backend.free(handle)

    def binary(self,a,b,dtype,mul=False):
        af=self.decode(a,dtype).tobytes();bf=self.decode(b,dtype).tobytes()
        out=self._f32_binary(af,bf,mul)
        return self.commit(self.encode(np.frombuffer(out,dtype='<f4'),dtype),'primitive_storage_round')

    def sum(self,parts,dtype):
        require(parts and len(parts[0])>0 and all(len(x)==len(parts[0]) for x in parts),'invalid target reduction')
        acc=self.decode(parts[0],dtype).tobytes()
        for part in parts[1:]:acc=self._f32_binary(acc,self.decode(part,dtype).tobytes())
        return self.commit(self.encode(np.frombuffer(acc,dtype='<f4'),dtype),'reduce_storage_round')

    def linear(self,activation,weight,m,k,n,dtype,layout,bias=None,_output_fp32=False):
        require(m>0 and m<=19 and 0<k<=4096 and 0<n<=4096,'matrix outside reviewed SRAM primitive')
        require(len(activation)==m*k*2 and len(weight)==k*n*2,'live matrix extent mismatch')
        require(layout in ('input_major','output_major','source','source_row_major'),'unknown matrix layout')
        require(bias is None or len(bias)==n*2,'bias extent mismatch')
        begin=self.backend.clock;handles=[];backend=self.backend
        try:
            # Actual source 16-bit operands are installed and read before the
            # explicit (currently unbilled) CPU expansion service.
            a16=backend.stage(self.partition,activation);handles.append(a16)
            source_hash=hashlib.sha256(weight).hexdigest()
            parameter=self.label.startswith('model.layers.')
            cache_key=(self.partition,self.label,k,n,dtype,layout,source_hash)
            if parameter:
                if cache_key not in self.weight_cache:
                    role=2 if self.label.endswith(('.mlp.gate','.shared_expert_gate')) else 1
                    self.weight_cache[cache_key]=backend.stage(self.partition,weight,role)
                w16=self.weight_cache[cache_key]
            else:
                w16=backend.stage(self.partition,weight);handles.append(w16)
            x=self.decode(backend.get(a16),dtype).reshape(m,k)
            actual_weight=backend.get(w16)
            require(hashlib.sha256(actual_weight).hexdigest()==source_hash,'live weight payload changed; never repair from checkpoint')
            w=self.decode(actual_weight,dtype)
            w=w.reshape(k,n).T.copy() if layout=='input_major' else w.reshape(n,k)
            ah=backend.stage(self.partition,x.tobytes());handles.append(ah)
            wh=backend.stage(self.partition,w.tobytes());handles.append(wh)
            ch=backend.alloc(self.partition,m*n*4);handles.append(ch)
            backend.rpc(5,ah,wh,ch,m,n,k,int(dtype=='F16'));out=backend.get(ch)
            if bias is not None:
                bias16=backend.stage(self.partition,bias);handles.append(bias16)
                b=self.decode(backend.get(bias16),dtype)
                expanded=np.broadcast_to(b,(m,n)).astype('<f4').tobytes()
                out=self._f32_binary(out,expanded)
            result=self.commit(out if _output_fp32 else self.encode(np.frombuffer(out,dtype='<f4'),dtype),
                               'linear_FP32_partial' if _output_fp32 else 'linear_storage_round')
            self.calls.append({'kind':'live_matrix','partition':self.partition,'label':self.label,'MKN':[m,k,n],
                'dtype':dtype,'output_dtype':'F32' if _output_fp32 else dtype,'bias':bias is not None,'start':begin,'complete':backend.clock,
                'source_sha256':hashlib.sha256(weight).hexdigest(),'output_sha256':hashlib.sha256(result).hexdigest(),
                'source_weight_handle':w16,'expanded_weight_handle':wh,'FP32_result_handle':ch,
                'CPU_codec_cost_verified':False})
            return result
        finally:
            for handle in reversed(handles):backend.free(handle)

    def linear_fp32(self,activation,weight,m,k,n,dtype,layout,bias=None):
        return self.linear(activation,weight,m,k,n,dtype,layout,bias,_output_fp32=True)

    def sum_fp32(self,parts):
        require(parts and len(parts[0])>0 and len(parts[0])%4==0 and all(len(p)==len(parts[0]) for p in parts),
                'FP32 collective extent differs')
        value=parts[0]
        for part in parts[1:]:value=self._f32_binary(value,part)
        return self.commit(value,'FP32_collective_commit')

    def copy(self,data):return self.commit(data,'local_copy')

    def close_weights(self):
        for handle in self.weight_cache.values():self.backend.free(handle)
        self.weight_cache.clear()


class CoupledTransport:
    target_noc=True
    def __init__(self,native):self.native=native;self.events=[]
    def send(self,src,dst,token,stage,payload):
        require(src!=dst and payload,'invalid coupled transfer')
        b=self.native.backend;handles=[];begin=b.clock
        try:
            source=b.stage(src,payload);handles.append(source)
            destination=b.alloc(dst,len(payload));handles.append(destination)
            b.rpc(7,source,destination,len(payload));actual=b.get(destination)
            require(actual==payload,'NoC/HB payload changed')
            self.events.append({'src':src,'dst':dst,'token':token,'stage':stage,'bytes':len(payload),
                 'payload_sha256':hashlib.sha256(actual).hexdigest(),'start':begin,'complete':b.clock,
                 'backend':'live PopNet + destination DRAM commit','target_noc':True})
            self.native.select_partition(dst,stage)
            return actual
        finally:
            for handle in reversed(handles):b.free(handle)
