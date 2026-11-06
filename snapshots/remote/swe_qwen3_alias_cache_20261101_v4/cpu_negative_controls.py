import ctypes as C,json,subprocess,re,hashlib
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;u=C.CDLL(str(R/'libcpu_probe.so'));U=C.c_uint64;u.serve.argtypes=[U,C.c_void_p,U,C.c_void_p,U,U,U,U];u.init.argtypes=[C.c_char_p];assert u.init(str(R).encode())==0
def refused(kind,blob,n,a=0,b=0,c=0):
 x=np.frombuffer(blob,dtype='u1').copy();y=np.zeros(n,dtype='u1');assert u.serve(kind,x.ctypes.data,x.size,y.ctypes.data,y.size,a,b,c)==-1
refused(1,b'\0\0',8,2)
refused(5,np.full(128,0x7fc0,dtype='<u2').tobytes(),512,1,128,1)
refused(14,np.asarray([18],dtype='<i8').tobytes(),8,0,19,1)
refused(8,b'\0\0'+np.asarray([1],dtype='<i8').tobytes(),2,1,2,1)
blob=np.zeros(4,dtype='<u2').tobytes()+np.asarray([0,0],dtype='<i8').tobytes()+np.zeros(4,dtype='<u2').tobytes();refused(9,blob,8,2,2,2)
refused(999,b'',1)
asm=subprocess.check_output(['objdump','-d',str(R/'host')],text=True);wide=re.findall(r'%[yz]mm\d+',asm);avx=re.findall(r'\t(v[a-z0-9]+)\s',asm);assert not wide and not avx
out=dict(state='PASS_LIMITED_CPU_PROTOCOL_AND_BINARY_ISA_CONTROLS',refused=['decode_length_mismatch','softmax_NaN','cached_KV_wrong_position','gather_bounds','index_add_duplicates','unknown_service'],host_binary_sha256=hashlib.sha256((R/'host').read_bytes()).hexdigest(),AVX_mnemonics=len(avx),YMM_ZMM_registers=len(wide),CLFLUSH_instructions=len(re.findall(r'\bclflush\b',asm)),MFENCE_instructions=len(re.findall(r'\bmfence\b',asm)),scope='compiled target binary only; dynamically dispatched libc ISA and cache-maintenance model coverage remain unverified')
(R/'CPU_CONTROLS_ISA.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
