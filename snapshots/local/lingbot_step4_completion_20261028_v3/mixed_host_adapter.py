"""Opt-in original-format host adapter. GPU-exact whole-layer gate is PARTIAL.

No GPU driver, model load, Golden tensor or recorded ID lookup is present.
Independent BF16 C arithmetic is admitted only for measured geometries and the
single-thread CPU source contract. Unsupported target paths fail explicitly.
"""
import ctypes
import pathlib
import json
import numpy as np
import torch
import torch.nn.functional as F


def require_host(*xs):
    for x in xs:
        if x.device.type!='cpu' or x.requires_grad:raise ValueError('CPU inference only')
        if x.dtype in (torch.float16,torch.float64):raise TypeError('original BF16/FP32 only')


def rne_bf16(x):
    require_host(x)
    if x.dtype!=torch.float32:raise TypeError('FP32 codec input')
    if not bool(torch.isfinite(x).all()):raise ValueError('certified finite-only codec domain')
    u=x.contiguous().view(torch.int32).long()&0xffffffff
    return (((u+0x7fff+((u>>16)&1))>>16)&0xffff).to(torch.uint16).view(torch.bfloat16)


def cuda_mean_square2048(x):
    require_host(x)
    if x.dtype!=torch.bfloat16 or x.shape[-1]!=2048:raise TypeError('registered BF16 H2048 only')
    z=x.float().square().reshape(-1,16,32,4)
    acc=torch.zeros((len(z),32,4),dtype=torch.float32)
    for i in range(16):acc=acc+z[:,i]
    v=((acc[:,:,0]+acc[:,:,1])+acc[:,:,2])+acc[:,:,3]
    for _ in range(5):v=v[:,0::2]+v[:,1::2]
    return (v/2048).reshape(*x.shape[:-1],1)


class MixedHostAdapter:
    def __init__(self,library,geometries):
        self.lib=ctypes.CDLL(str(pathlib.Path(library).resolve()))
        self.lib.source_gemm.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int]*3
        self.geometries={tuple(g) for g in json.loads(pathlib.Path(geometries).read_text())['BF16_bias_free_MNK']}
        self.operations=[]
        self.host_GiB=128;self.HB_GiB=8;self.target_GPU_count=0

    def linear(self,x,w,bias=None):
        require_host(x,w)
        if w.ndim!=2 or x.ndim<1 or x.shape[-1]!=w.shape[-1]:raise ValueError('linear shape contract')
        if torch.get_num_threads()!=1:raise RuntimeError('single-thread source arithmetic contract required')
        if x.dtype!=w.dtype or x.dtype not in (torch.bfloat16,torch.float32):raise TypeError('canonical linear dtype')
        if bias is not None:
            require_host(bias)
            if bias.dtype!=w.dtype:raise TypeError('canonical bias dtype')
            if bias.shape!=(len(w),):raise ValueError('bias shape contract')
        shape=x.shape[:-1]+(len(w),);flat=x.reshape(-1,x.shape[-1]).contiguous()
        if x.dtype==torch.float32:
            # Explicit CPU fallback, NOT a certified GPU cuBLAS or NPU GEMM.
            out=F.linear(flat,w,bias)
            self.operations.append(dict(op='FP32_linear',execution='host_CPU_fallback',GPU_exact=False,cycles=None))
        else:
            if bias is not None:raise NotImplementedError('BF16 bias-fused rounding not admitted')
            geometry=(len(flat),len(w),flat.shape[1])
            if geometry not in self.geometries:raise NotImplementedError(('unvalidated BF16 geometry',geometry))
            w=w.contiguous();out=torch.empty((len(flat),len(w)),dtype=torch.float32)
            assert self.lib.source_gemm(flat.data_ptr(),w.data_ptr(),out.data_ptr(),*geometry)==0
            out=rne_bf16(out)
            self.operations.append(dict(op='BF16_source_C_GEMM',geometry=geometry,execution='host_CPU_software_FP32',GPU_exact=False,cycles=None))
        return out.reshape(shape)

    def silu(self,x):
        require_host(x)
        if x.dtype!=torch.bfloat16:raise TypeError('original BF16 activation boundary')
        z=x.float().contiguous().numpy()
        with np.errstate(over='ignore',under='ignore',invalid='ignore',divide='ignore'):
            y=z/(np.float32(1)+np.exp(-z,dtype=np.float32))
        out=rne_bf16(torch.from_numpy(y))
        self.operations.append(dict(op='BF16_SiLU',execution='host_CPU_FP32_exp_software',GPU_exact=False,cycles=None))
        return out

    def mlp(self,x,w1,w3,w2):
        gate=self.linear(x,w1);up=self.linear(x,w3)
        product=rne_bf16(self.silu(gate).float()*up.float())
        return self.linear(product,w2)

    def rms_gpu_exact(self,x,w):
        require_host(x,w)
        raise NotImplementedError('GPU rsqrt.approx bit semantics not implemented; mean(square) alone is exact')

    def sigmoid_gpu_exact(self,x):
        require_host(x)
        raise NotImplementedError('GPU exp.approx/FP32 sigmoid bit semantics not implemented')
