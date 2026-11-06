"""CPU-only immutable hardware-function profiles; no workload/GPU lookups.

Stored values are original FP32 bit patterns. Profiles are acquired over whole
instruction domains independent of model inputs. No FP64 model arithmetic.
"""
import pathlib
import numpy as np


class SFUProfile:
    def __init__(self,directory):
        root=pathlib.Path(directory)
        self.even=np.memmap(root/'rsq_exp127.raw',dtype='<u4',mode='r')
        self.odd=np.memmap(root/'rsq_exp128.raw',dtype='<u4',mode='r')
        if len(self.even)!=2**23 or len(self.odd)!=2**23:raise ValueError('incomplete architecture RSQ domain')
        self.ex2_path=root/'ex2_all_f32.raw';self.ex2=None
        self.target_GPU_count=0

    def rsqrt(self,x):
        if not isinstance(x,np.ndarray) or x.dtype!=np.float32:raise TypeError('CPU FP32 input required')
        u=np.ascontiguousarray(x).view(np.uint32)
        exponent=((u>>23)&255).astype(np.int32)
        if np.any(u>>31) or np.any(exponent==0) or np.any(exponent==255):raise ValueError('registered positive-normal FP32 RSQ domain only')
        e=exponent-127;m=u&0x7fffff
        normalized=np.where((e&1)==0,self.even[m],self.odd[m])
        # Floor division is essential for negative odd unbiased exponents.
        adjusted=normalized.astype(np.int64)-(e//2).astype(np.int64)*(1<<23)
        return adjusted.astype(np.uint32).view(np.float32).reshape(x.shape)

    def exp2(self,x):
        if not isinstance(x,np.ndarray) or x.dtype!=np.float32:raise TypeError('CPU FP32 input required')
        if self.ex2 is None:
            if self.ex2_path.stat().st_size!=2**34:raise ValueError('incomplete full FP32 EX2 profile')
            self.ex2=np.memmap(self.ex2_path,dtype='<u4',mode='r')
        return self.ex2[np.ascontiguousarray(x).view(np.uint32)].view(np.float32).reshape(x.shape)
