import os,pathlib,json,ctypes as C,hashlib,numpy as np
R=pathlib.Path(__file__).resolve().parent;roundfile=R/'ROUND_N00';roundno=int(roundfile.read_text())+1 if roundfile.exists() else 1;roundfile.write_text(str(roundno));D=R/('case'+str(roundno));D.mkdir(exist_ok=True);N=D/'N00';N.mkdir(exist_ok=False);u=C.CDLL(str(R/'libpeer.so'));U=C.c_uint64;u.um_init.argtypes=[C.c_char_p];u.um_error.restype=C.c_char_p;u.um_now.restype=U
for n in ['um_store','um_sram_load']:getattr(u,n).argtypes=[U,C.c_void_p,U]
for n in ['um_net_send','um_net_recv']:getattr(u,n).argtypes=[C.c_void_p,U]
def ck(rc):
 if rc:raise RuntimeError(u.um_error().decode())
def sha(a):return hashlib.sha256(a.tobytes()).hexdigest()
log=[]
def hb(a,addr,label):
 a=np.ascontiguousarray(a);b=np.empty_like(a);start=int(u.um_now());ck(u.um_store(addr,a.ctypes.data,a.nbytes));ck(u.um_sram_load(addr,b.ctypes.data,b.nbytes));assert np.array_equal(a.view(np.uint8),b.view(np.uint8));log.append(dict(kind='HB',label=label,start=start,done=int(u.um_now()),bytes=a.nbytes,sha256=sha(b)));return b
def tx(a,label):
 a=np.ascontiguousarray(a);t=int(u.um_now());ck(u.um_net_send(a.ctypes.data,a.nbytes));log.append(dict(kind='send',label=label,start=t,done=int(u.um_now()),bytes=a.nbytes,sha256=sha(a)))
def rx(n,label):
 a=np.empty(n,dtype=np.uint8);t=int(u.um_now());ck(u.um_net_recv(a.ctypes.data,n));log.append(dict(kind='recv',label=label,start=t,done=int(u.um_now()),bytes=n,sha256=sha(a)));return a
ck(u.um_init(str(N).encode()))
for i,(name,out,K) in enumerate([('K',128,2048),('V',128,2048),('Ocarry',2048,128)]):
 mode=i==2;header=np.array([2 if mode else 1,i,out,K,K*2,K*out*2,out*4 if mode else 0,out*2 if mode else 0],dtype=np.uint64);x=hb(np.fromfile(R/'data'/(name+'_x.bin'),dtype=np.uint8),0,name+'_x');w=hb(np.fromfile(R/'data'/(name+'_w.bin'),dtype=np.uint8),2**20,name+'_w');tx(header,name+'_header');tx(x,name+'_x');tx(w,name+'_w')
 if mode:tx(hb(np.fromfile(R/'data/Ocarry_initial.bin',dtype=np.uint8),8*2**20,'carry'),'carry');tx(hb(np.fromfile(R/'data/Ocarry_bias.bin',dtype=np.uint8),9*2**20,'bias'),'bias')
 response=rx(64,name+'_response_header').view(np.uint64);assert np.array_equal(response,header);raw=rx(out*4,name+'_F32');bf=rx(out*2,name+'_BF16');recv_done=int(u.um_now());raw=hb(raw,16*2**20,name+'_F32_commit');bf=hb(bf,20*2**20,name+'_BF16_commit');assert int(u.um_now())>=recv_done;assert raw.tobytes()==(R/'data'/(name+'_F32_reference.bin')).read_bytes();assert bf.tobytes()==(R/'data'/(name+'_GPU.bin')).read_bytes();(N/(name+'_F32.bin')).write_bytes(raw.tobytes());(N/(name+'_BF16.bin')).write_bytes(bf.tobytes())
ck(u.um_sram_finish());ck(u.um_shutdown());(N/'EVENTS.json').write_text(json.dumps(log,indent=2));(N/'PASS.json').write_text(json.dumps(dict(state='PASS_CPU_CALLBACK_RECEIVE_BEFORE_CONSUME',GPU_count=0,FP32_reference_elements=2304,BF16_GPU_elements=2304),indent=2))
