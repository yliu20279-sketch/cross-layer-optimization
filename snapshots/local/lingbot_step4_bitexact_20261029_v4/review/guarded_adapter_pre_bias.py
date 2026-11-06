"""Guarded CPU adapter for the admitted LingBot layer0 geometries only."""
import numpy as np
from target_math_simd import rms as _rms,linear as _linear,rb

def original_bf16(x):
 if not isinstance(x,np.ndarray) or x.dtype!=np.float32:raise TypeError('CPU FP32 containers of original BF16 required')
 if not np.isfinite(x).all():raise ValueError('finite admitted data only')
 if np.any(x.view(np.uint32)&0xffff):raise ValueError('original BF16 grid required')

def rms(x,w):
 original_bf16(x)
 if x.shape[-1] not in [128,2048]:raise ValueError('unadmitted RMS width')
 if not isinstance(w,np.ndarray) or w.dtype!=np.float32:raise TypeError('original FP32 norm weight required')
 if w.shape!=(x.shape[-1],) or not np.isfinite(w).all():raise ValueError('invalid norm weight')
 return _rms(x,w)

def linear(x,w,bias=None):
 original_bf16(x);original_bf16(w)
 if bias is not None:raise ValueError('bias not admitted by current source geometry')
 if x.ndim!=2 or w.ndim!=2:raise ValueError('matrix operands required')
 if x.shape[1]!=w.shape[1] or (w.shape[1],w.shape[0]) not in [(2048,2048),(2048,768),(768,2048)] or not 0<len(x)<=49883:raise ValueError('unadmitted GEMM geometry')
 return _linear(x,w)
