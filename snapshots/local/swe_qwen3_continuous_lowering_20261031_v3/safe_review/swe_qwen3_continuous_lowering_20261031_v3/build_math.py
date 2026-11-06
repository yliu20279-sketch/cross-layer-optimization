import json,hashlib,ctypes as C,os,time
from pathlib import Path
import numpy as np,torch
R=Path(__file__).resolve().parent;B=R.parent;torch.set_num_threads(1)
lib=B/'swe_qwen3_softmax_primitive_20261029_v1/libstage_reference.so';u=C.CDLL(str(lib));u.source_exp16.argtypes=[C.c_void_p,C.c_void_p,C.c_int,C.c_int]
p=R/'EXP16_ALL_FP32.bin';assert not p.exists();start=time.time();chunk=2**22
with p.open('wb') as f:
 for off in range(0,2**32,chunk):
  bits=np.arange(off,off+chunk,dtype='<u4');out=np.empty(chunk,dtype='<f4');u.source_exp16(bits.ctypes.data,out.ctypes.data,1,chunk);f.write(out.tobytes())
  if off%(chunk*64)==0:(R/'MATH_PROGRESS.json').write_text(json.dumps(dict(next_bits=off+chunk,total_bits=2**32,elapsed_seconds=time.time()-start)))
 f.flush();os.fsync(f.fileno())
assert p.stat().st_size==2**34
bits=np.arange(65536,dtype='<u2');x=torch.from_numpy(bits).view(torch.bfloat16);y=torch.nn.functional.silu(x);(R/'SILU_ALL_BF16.bin').write_bytes(y.view(torch.uint16).numpy().tobytes())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while a:=f.read(8*2**20):h.update(a)
 return h.hexdigest()
# Mixed-lane independent query of the original library after construction.
table=np.memmap(p,dtype='<f4',mode='r');rng=np.random.default_rng(3101);query=np.concatenate([rng.integers(0,2**32,65536,dtype='<u4'),np.arange(0,2**32,65536,dtype='<u4')]);gold=np.empty(query.size,dtype='<f4');u.source_exp16(query.ctypes.data,gold.ctypes.data,1,query.size);assert np.array_equal(gold.view('<u4'),table[query].view('<u4'))
out=dict(state='PASS_MODEL_INDEPENDENT_FULL_BIT_DOMAIN_TABLES',EXP32=dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p),entries=2**32),SILU16=dict(path=str(R/'SILU_ALL_BF16.bin'),bytes=131072,sha256=sha(R/'SILU_ALL_BF16.bin'),entries=65536),source=str(lib),source_sha256=sha(lib),mixed_lane_queries=query.size,scope='complete instruction-domain compatibility data, not model inputs or output-specific corrections; same original SLEEF dependency',elapsed_seconds=time.time()-start)
(R/'MATH_STATUS.json').write_text(json.dumps(out,indent=2));print(json.dumps(out),flush=True)
