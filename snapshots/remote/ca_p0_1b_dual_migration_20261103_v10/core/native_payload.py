"""Bound native CPU functional substrate, never a target timing backend."""
import ctypes
import hashlib
from pathlib import Path
import numpy as np
from .common import require


class NativePayload:
    scope = 'native CPU functional payload; target opcode/timing not verified'

    def __init__(self, library, expected_sha256):
        p = Path(library)
        require(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == expected_sha256,
                'native payload library identity changed')
        self.lib = ctypes.CDLL(str(p.resolve()))
        self.sha256 = expected_sha256
        ptr, u64, integer = ctypes.c_void_p, ctypes.c_uint64, ctypes.c_int
        signatures = {'p0_codec': [ptr,ptr,u64,integer], 'p0_round': [ptr,ptr,u64,integer],
                      'p0_copy': [ptr,ptr,u64], 'p0_sum': [ptr,ptr,u64,u64,integer],
                      'p0_linear': [ptr,ptr,ptr,ptr,u64,u64,u64,integer,integer]}
        for name, args in signatures.items():
            fn = getattr(self.lib, name); fn.argtypes = args; fn.restype = integer
        self.calls = []

    @staticmethod
    def dtype(value):
        require(value in ('F16','BF16'), 'explicit native dtype required')
        return 0 if value == 'F16' else 1

    def decode(self, data, dtype):
        require(len(data) > 0 and len(data)%2 == 0, 'invalid 16-bit bytes')
        a = np.frombuffer(data, dtype='<u2').copy()
        out = np.empty(a.size, dtype='<f4')
        require(self.lib.p0_codec(a.ctypes.data, out.ctypes.data, a.size, self.dtype(dtype)) == 0, 'codec failed')
        return out

    def encode(self, data, dtype):
        a = np.ascontiguousarray(data, dtype='<f4').reshape(-1)
        require(a.size > 0, 'empty numeric payload')
        out = np.empty(a.size, dtype='<u2')
        require(self.lib.p0_round(a.ctypes.data, out.ctypes.data, a.size, self.dtype(dtype)) == 0, 'round failed')
        return out.tobytes()

    def copy(self, data):
        require(bool(data), 'empty transfer')
        a = np.frombuffer(data, dtype='u1').copy(); out = np.empty_like(a)
        require(self.lib.p0_copy(a.ctypes.data, out.ctypes.data, a.size) == 0, 'copy failed')
        self.calls.append({'kind':'payload_copy','bytes':len(data)})
        return out.tobytes()

    def sum(self, parts, dtype):
        require(parts and len(parts[0]) > 0 and len(parts[0])%2 == 0 and
                all(len(p) == len(parts[0]) for p in parts), 'invalid reduction extents')
        a = np.frombuffer(b''.join(parts), dtype='<u2').copy(); out = np.empty(len(parts[0])//2,dtype='<u2')
        require(self.lib.p0_sum(a.ctypes.data,out.ctypes.data,len(parts),out.size,self.dtype(dtype)) == 0, 'reduce failed')
        self.calls.append({'kind':'ordered_sum','ranks':len(parts),'bytes':len(parts[0])})
        return out.tobytes()

    def linear(self, activation, weight, m, k, n, dtype, layout, bias=None):
        require(layout in ('input_major','output_major','source_row_major'), 'unknown weight layout')
        require(m > 0 and k > 0 and n > 0 and len(activation) == m*k*2 and len(weight) == k*n*2,
                'linear operand extent mismatch')
        require(bias is None or len(bias) == n*2, 'bias extent mismatch')
        a=np.frombuffer(activation,dtype='<u2').copy(); b=np.frombuffer(weight,dtype='<u2').copy()
        bias_array=None if bias is None else np.frombuffer(bias,dtype='<u2').copy()
        out=np.empty(m*n,dtype='<u2')
        status=self.lib.p0_linear(a.ctypes.data,b.ctypes.data,None if bias_array is None else bias_array.ctypes.data,
                                  out.ctypes.data,m,k,n,self.dtype(dtype),int(layout!='input_major'))
        require(status == 0, 'native linear failed')
        self.calls.append({'kind':'linear','MKN':[m,k,n],'dtype':dtype,'bias':bias is not None})
        return out.tobytes()
