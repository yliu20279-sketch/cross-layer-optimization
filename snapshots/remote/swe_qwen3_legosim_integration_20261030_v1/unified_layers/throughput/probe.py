import ctypes as C,numpy as np,time,json
from pathlib import Path
R=Path(__file__).resolve().parent;l=C.CDLL(str(R.parent/'libunified.so'));U=C.c_uint64;l.um_init.argtypes=[C.c_char_p];l.um_store.argtypes=[U,C.c_void_p,U];l.um_load.argtypes=[U,C.c_void_p,U];l.um_error.restype=C.c_char_p
assert l.um_init(str(R/'reports').encode())==0
x=np.arange(1048576,dtype='<u2');y=np.empty_like(x);start=time.monotonic();assert l.um_store(1048576,x.ctypes.data,x.nbytes)==0,l.um_error();assert l.um_load(1048576,y.ctypes.data,y.nbytes)==0,l.um_error();assert np.array_equal(x,y);elapsed=time.monotonic()-start;assert l.um_shutdown()==0
(R/'RESULTS.json').write_text(json.dumps(dict(bytes_each_direction=x.nbytes,wall_seconds=elapsed,exact=True)))
