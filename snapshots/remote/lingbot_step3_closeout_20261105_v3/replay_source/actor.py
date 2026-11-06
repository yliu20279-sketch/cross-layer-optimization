import os,pathlib,json,ctypes as C,hashlib,numpy as np
from completion_gate import CompletionGate
R=pathlib.Path(__file__).resolve().parent
roundfile=R/'ROUND_N00'
roundno=int(roundfile.read_text())+1 if roundfile.exists() else 1
roundfile.write_text(str(roundno))
branch='cond' if roundno==1 else 'uncond'
D=R/('case'+str(roundno));D.mkdir(exist_ok=True);N=D/'N00';N.mkdir()
data=R/'data'/branch
u=C.CDLL(str(R/'libpeer.so'));U=C.c_uint64
u.um_init.argtypes=[C.c_char_p];u.um_error.restype=C.c_char_p;u.um_now.restype=U
for name in ('um_store','um_sram_load'):getattr(u,name).argtypes=[U,C.c_void_p,U]
for name in ('um_net_send','um_net_recv'):getattr(u,name).argtypes=[C.c_void_p,U]
def ck(rc):
    if rc:raise RuntimeError(u.um_error().decode())
def hb(a,addr):
    b=np.empty_like(a);ck(u.um_store(addr,a.ctypes.data,a.nbytes));ck(u.um_sram_load(addr,b.ctypes.data,b.nbytes))
    assert a.tobytes()==b.tobytes()
    return b
events=[]
def tx(a):
    ck(u.um_net_send(a.ctypes.data,a.nbytes))
def rx(n,label):
    a=np.empty(n,np.uint8);start=int(u.um_now());ck(u.um_net_recv(a.ctypes.data,n))
    events.append(dict(label=label,start=start,done=int(u.um_now()),bytes=n))
    return a
ck(u.um_init(str(N).encode()))
header=np.array([1,0,128,2048,4096,524288,0,0],dtype=np.uint64)
x=hb(np.fromfile(data/'K_x.bin',np.uint8),0)
w=hb(np.fromfile(data/'K_w.bin',np.uint8),2**20)
tx(header);tx(x);tx(w)
response=rx(64,'cpu_return').view(np.uint64);assert np.array_equal(response,header)
cpu_done=int(u.um_now())
raw=rx(512,'raw_result');bf=rx(256,'noc_result_tail')
ack=rx(64,'writeback_receipt').view(np.uint64)
assert ack.tolist()==[0x534d4344,roundno,0,128,512,256,1,0]
identity=dict(request='example_4',cfg=branch,step=0,layer=0,token=0,version=1)
gate=CompletionGate(identity,{kind:0 for kind in ('cpu_return','dma_poll_complete','dirty_writeback_callback','noc_receive_tail')})
# Gateway response-header receive follows request DMA; result tail follows response DMA.
for kind,t in [('cpu_return',cpu_done),('dma_poll_complete',events[2]['done']),
               ('dirty_writeback_callback',events[3]['done']),('noc_receive_tail',events[3]['done'])]:
    gate.accept(kind,identity,0,t,'1')
ready=gate.release(int(u.um_now()))
start=int(u.um_now());raw=hb(raw,16*2**20);bf=hb(bf,20*2**20)
assert raw.tobytes()==(data/'K_F32_reference.bin').read_bytes()
assert bf.tobytes()==(data/'K_GPU.bin').read_bytes()
(N/'K_F32.bin').write_bytes(raw.tobytes());(N/'K_BF16.bin').write_bytes(bf.tobytes())
ck(u.um_sram_finish());ck(u.um_shutdown())
(N/'EVENTS.json').write_text(json.dumps(events,indent=2))
(N/'GATE.json').write_text(json.dumps(dict(identity=identity,completed=gate.completed,ready_ns=ready,consumer_start_ns=start,consumer_done_ns=int(u.um_now())),indent=2))
(N/'PASS.json').write_text(json.dumps(dict(state='PASS_LIMITED_BRANCH_K',branch=branch,fp32_elements=128,bf16_gpu_elements=128)))
