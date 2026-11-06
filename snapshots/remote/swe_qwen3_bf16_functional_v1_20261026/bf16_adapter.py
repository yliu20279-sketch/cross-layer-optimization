"""CPU-only per-operator Qwen3 BF16 semantic adapter.

No model downloader, checkpoint loader, training, timing estimate, NPU driver,
or simulator. Native BF16 boundaries reuse the audited NPUSim codec via ctypes.
PyTorch CPU kernels supply functional arithmetic, not target hardware timing.
"""
import ctypes
from pathlib import Path
import sys
import numpy as np
import torch
import torch.nn.functional as F


class NativeCodec:
    def __init__(self, library):
        if sys.byteorder != 'little':
            raise RuntimeError('Little-endian payload platform required')
        self.library = str(Path(library).resolve())
        self.lib = ctypes.CDLL(self.library)
        self.lib.swe_bf16_encode.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        self.lib.swe_bf16_encode.restype = None
        self.lib.swe_bf16_decode.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        self.lib.swe_bf16_decode.restype = None

    def round(self, x):
        cpu_only(x)
        if x.dtype not in (torch.bfloat16, torch.float32):
            raise TypeError('BF16 conversion of integer metadata is forbidden')
        a = x.detach().to(torch.float32).contiguous().numpy()
        bits = np.empty(a.shape, dtype=np.uint16)
        self.lib.swe_bf16_encode(a.ctypes.data, bits.ctypes.data, a.size)
        return torch.from_numpy(bits).view(torch.bfloat16)

    def decode(self, x):
        require_bf16(x)
        bits = x.detach().contiguous().view(torch.uint16).numpy()
        out = np.empty(bits.shape, dtype=np.float32)
        self.lib.swe_bf16_decode(bits.ctypes.data, out.ctypes.data, bits.size)
        return torch.from_numpy(out)


def cpu_only(*xs):
    for x in xs:
        if x.device.type != 'cpu' or x.requires_grad:
            raise ValueError('Inference-only CPU tensors required')


def require_bf16(*xs):
    cpu_only(*xs)
    if any(x.dtype != torch.bfloat16 for x in xs):
        raise TypeError('Original BF16 tensor required, no implicit FP16/FP32 model substitution')


def require_indices(x):
    cpu_only(x)
    if x.dtype != torch.int64:
        raise TypeError('Index/position metadata must remain int64')


class AppendOnlyKV:
    """Session/layer-scoped BF16 dynamic cache; append-only pilot semantics.

    Static/paged/sliding-window cache, cross-process prefix sharing and eviction
    are outside this functional adapter, not silently approximated.
    """
    def __init__(self):
        self.entries = {}

    def length(self, session, layer):
        entry = self.entries.get((session, layer))
        return 0 if entry is None else entry[0].shape[-2]

    def append(self, session, layer, key, value, positions):
        require_bf16(key, value); require_indices(positions)
        if key.ndim != 4 or key.shape != value.shape or positions.ndim != 1:
            raise ValueError('Expected K,V[B,KVH,T,D] and positions[T]')
        old = self.entries.get((session, layer)); past = self.length(session, layer)
        expected = torch.arange(past, past + key.shape[-2], dtype=torch.int64)
        if not torch.equal(positions, expected):
            raise ValueError('Non-contiguous cache positions/retries are not silently appended')
        if old is not None:
            if old[0].shape[:2] + old[0].shape[-1:] != key.shape[:2] + key.shape[-1:]:
                raise ValueError('KV geometry changed within session/layer')
            k = torch.cat((old[0], key), dim=-2); v = torch.cat((old[1], value), dim=-2)
        else:
            k, v = key.clone(), value.clone()
        self.entries[(session, layer)] = (k, v)
        return k.clone(), v.clone()


class BF16Adapter:
    def __init__(self, codec):
        self.codec = codec
        self.events = []

    def note(self, name, tensor, **metadata):
        self.events.append(dict(op=name, dtype=str(tensor.dtype), shape=list(tensor.shape),
                                bytes=tensor.numel()*tensor.element_size(),
                                functional_device='CPU', timing='UNMODELED', **metadata))
        return tensor

    def cast(self, x, dtype):
        cpu_only(x)
        if dtype == torch.bfloat16:
            return self.note('cast_bf16_native_codec', self.codec.round(x))
        if dtype == torch.float32 and x.is_floating_point():
            out = self.codec.decode(x) if x.dtype == torch.bfloat16 else x.to(dtype)
            return self.note('cast_fp32', out)
        if dtype == torch.int64 and x.dtype == torch.int64:
            return self.note('preserve_int64', x.clone())
        raise TypeError('Only explicit BF16/FP32 float casts and identity int64 are supported')

    def linear(self, x, weight):
        require_bf16(x, weight)
        if weight.ndim != 2 or x.shape[-1] != weight.shape[-1]:
            raise ValueError('Linear weight must be [out,in]')
        # Same API-level BF16 CPU backend as the source nn.Linear; internal
        # reduction/FMA is backend-defined, not certified target FP32 MAC.
        return self.note('linear_bf16_cpu_backend', self.codec.round(F.linear(x, weight)),
                         kernel_accumulation='backend_defined_not_target_certified')

    def matmul(self, a, b):
        require_bf16(a, b)
        return self.note('matmul_bf16_cpu_backend', self.codec.round(torch.matmul(a, b)),
                         kernel_accumulation='backend_defined_not_target_certified')

    def add(self, a, b):
        require_bf16(a, b)
        return self.note('add_bf16', self.codec.round(a.float() + b.float()))

    def multiply(self, a, b):
        require_bf16(a, b)
        return self.note('mul_bf16', self.codec.round(a.float() * b.float()))

    def rmsnorm(self, x, scale, epsilon=1e-6):
        require_bf16(x, scale)
        if scale.ndim != 1 or scale.numel() != x.shape[-1] or epsilon < 0:
            raise ValueError('RMS scale must be a shared last-dimension vector')
        fp = self.cast(x, torch.float32)
        variance = self.note('rms_variance_fp32', fp.pow(2).mean(-1, keepdim=True))
        inverse = self.note('rms_rsqrt_fp32', torch.rsqrt(variance + epsilon))
        normalized = self.cast(fp * inverse, torch.bfloat16)
        return self.note('rms_scale_after_bf16_cast', self.multiply(scale, normalized))

    def softmax_fp32(self, x, dim=-1):
        cpu_only(x)
        if x.dtype not in (torch.float32, torch.bfloat16):
            raise TypeError('Expected FP32/BF16 softmax input')
        return self.note('softmax_fp32_no_early_round', F.softmax(x, dim=dim, dtype=torch.float32))

    def topk(self, probabilities, k):
        cpu_only(probabilities)
        if probabilities.dtype != torch.float32 or not 0 < k <= probabilities.shape[-1]:
            raise ValueError('Router TopK requires FP32 probabilities and valid K')
        values, indices = torch.topk(probabilities, k, dim=-1)
        self.note('topk_fp32_values', values, tie_policy='backend_topk_unspecified_cross_backend')
        self.note('topk_int64_ids', indices)
        return values, indices

    def route(self, x, router_weight, top_k=8):
        shape = x.shape[:-1]; logits = self.linear(x.reshape(-1, x.shape[-1]), router_weight)
        probabilities = self.softmax_fp32(logits)
        values, ids = self.topk(probabilities, top_k)
        normalized = self.note('router_renormalize_fp32', values / values.sum(-1, keepdim=True))
        weights = self.cast(normalized, torch.bfloat16)
        return dict(logits=logits, probabilities=probabilities, selected=ids,
                    weights=weights, original_token_shape=shape)

    def gather(self, data, indices, axis=0):
        """ONNX Gather shape semantics; negative indices normalized explicitly."""
        cpu_only(data); require_indices(indices)
        axis %= data.ndim; extent = data.shape[axis]
        if torch.any(indices < -extent) or torch.any(indices >= extent):
            raise IndexError('Gather index outside axis extent')
        normalized = indices.remainder(extent)
        out = torch.index_select(data, axis, normalized.reshape(-1))
        out = out.reshape(data.shape[:axis] + indices.shape + data.shape[axis+1:])
        return self.note('gather_preserve_dtype', out)

    def scatter_elements(self, data, indices, updates, axis=0, reduction='add'):
        cpu_only(data, updates); require_indices(indices)
        if updates.shape != indices.shape or data.dtype != updates.dtype:
            raise ValueError('Scatter requires matching index/update shape and dtype')
        axis %= data.ndim; normalized = indices.remainder(data.shape[axis])
        if torch.any(indices < -data.shape[axis]) or torch.any(indices >= data.shape[axis]):
            raise IndexError('Scatter index outside axis extent')
        if reduction == 'add':
            out = data.clone().scatter_add_(axis, normalized, updates)
        else:
            raise NotImplementedError('Only additive scatter is certified; duplicate replacement order is undefined')
        return self.note('scatter_elements_add_cpu_backend', out)

    def index_add(self, data, ids, updates, axis=0):
        cpu_only(data, updates); require_indices(ids)
        if ids.ndim != 1 or data.dtype != updates.dtype:
            raise ValueError('index_add requires 1D int64 IDs and matching dtype')
        return self.note('index_add_source_order_cpu_backend', data.clone().index_add_(axis, ids, updates))

    def expert(self, x, gate_weight, up_weight, down_weight):
        gate = self.linear(x, gate_weight); up = self.linear(x, up_weight)
        active = self.note('silu_bf16_fused_cpu_backend', self.codec.round(F.silu(gate)))
        product = self.multiply(active, up)
        return self.linear(product, down_weight)

    def moe(self, hidden, router_weight, expert_weights, top_k=8):
        require_bf16(hidden, router_weight)
        flat = hidden.reshape(-1, hidden.shape[-1])
        if len(expert_weights) != router_weight.shape[0]:
            raise ValueError('Expert table/router mismatch')
        route = self.route(flat, router_weight, top_k)
        output = torch.zeros_like(flat)
        counts = []
        # Ascending expert order and (slot,token) order match the captured
        # source function; no invented expert-ID tie-breaking policy.
        for expert, weights in enumerate(expert_weights):
            slots, tokens = torch.where(route['selected'].T == expert)
            counts.append(tokens.numel())
            if tokens.numel() == 0:
                continue
            state = self.gather(flat, tokens, 0)
            result = self.expert(state, *weights)
            weighted = self.multiply(result, route['weights'][tokens, slots, None])
            output = self.index_add(output, tokens, weighted)
        if sum(counts) != flat.shape[0]*top_k:
            raise RuntimeError('Dispatch count conservation failed')
        route['counts'] = counts
        return self.note('moe_output', output.reshape_as(hidden)), route

    def rotary_tables(self, positions, inv_freq, output_dtype=torch.bfloat16):
        require_indices(positions); cpu_only(inv_freq)
        if positions.ndim != 2 or inv_freq.ndim != 1 or inv_freq.dtype != torch.float32:
            raise ValueError('positions[B,T] int64; inv_freq[D/2] FP32 must not be rounded as a weight')
        inv = inv_freq[None, :, None].expand(positions.shape[0], -1, 1)
        frequencies = (inv @ positions[:, None, :].float()).transpose(1, 2)
        embeddings = torch.cat((frequencies, frequencies), dim=-1)
        cos = self.note('rope_cos_fp32', embeddings.cos())
        sin = self.note('rope_sin_fp32', embeddings.sin())
        if output_dtype == torch.bfloat16:
            return self.cast(cos, output_dtype), self.cast(sin, output_dtype)
        if output_dtype == torch.float32:
            return cos, sin
        raise TypeError('No FP16 RoPE path')

    def apply_rotary(self, q, k, cos, sin):
        require_bf16(q, k, cos, sin)
        if q.shape[-1] % 2 or k.shape[-1] != q.shape[-1]:
            raise ValueError('Rotary head dimension must be even and match')
        cos, sin = cos.unsqueeze(1), sin.unsqueeze(1)
        def rotate(x):
            first, second = x.chunk(2, dim=-1)
            return torch.cat((-second, first), dim=-1)
        return (self.add(self.multiply(q, cos), self.multiply(rotate(q), sin)),
                self.add(self.multiply(k, cos), self.multiply(rotate(k), sin)))

    def attention(self, hidden, weights, heads, kv_heads, head_dim, positions,
                  cos, sin, mask, cache=None, session='default', layer=0):
        """Eager, eval-only GQA. No FlashAttention/SDPA equivalence claim."""
        require_bf16(hidden)
        if hidden.ndim != 3 or heads % kv_heads:
            raise ValueError('Expected [B,T,H], query heads divisible by KV heads')
        q_w,k_w,v_w,o_w,q_scale,k_scale = weights
        b,t,_ = hidden.shape
        q = self.rmsnorm(self.linear(hidden,q_w).reshape(b,t,heads,head_dim),q_scale).transpose(1,2)
        k = self.rmsnorm(self.linear(hidden,k_w).reshape(b,t,kv_heads,head_dim),k_scale).transpose(1,2)
        v = self.linear(hidden,v_w).reshape(b,t,kv_heads,head_dim).transpose(1,2)
        q,k = self.apply_rotary(q,k,cos,sin)
        if cache is not None:
            k,v = cache.append(session,layer,k,v,positions)
        repeat = heads//kv_heads
        rk = k.repeat_interleave(repeat,dim=1);rv = v.repeat_interleave(repeat,dim=1)
        scores = self.codec.round(self.matmul(q,rk.transpose(2,3))*(head_dim**-0.5))
        if mask is not None:
            require_bf16(mask)
            scores = self.add(scores,mask[:,:,:,:rk.shape[-2]])
        probabilities = self.cast(self.softmax_fp32(scores),torch.bfloat16)
        context = self.matmul(probabilities,rv).transpose(1,2).contiguous().reshape(b,t,heads*head_dim)
        return self.linear(context,o_w), probabilities
