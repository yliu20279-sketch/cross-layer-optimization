"""Legacy GPTQ int4 -> FP16 input-major weights. NumPy, CPU only.

    W[k,n] = FP16(FP32(q[k,n] - (stored_zero[group[k],n]+1)) * scale[group[k],n])
    g_idx is honored. No model forward, calibration or new quantization.
"""
import numpy as np
from .common import require


def decode(qweight, qzeros, scales, g_idx):
    a = np.asarray(qweight, dtype=np.int32).view(np.uint32)
    z = np.asarray(qzeros, dtype=np.int32).view(np.uint32)
    s = np.asarray(scales)
    g = np.asarray(g_idx, dtype=np.int64)
    require(a.ndim == z.ndim == s.ndim == 2 and g.ndim == 1, "invalid GPTQ ranks")
    require(len(g) == a.shape[0] * 8 and s.shape[1] == a.shape[1] and
            z.shape == (s.shape[0], (s.shape[1] + 7) // 8), "GPTQ shapes inconsistent")
    require(s.dtype == np.float16 and np.isfinite(s).all() and
            (g >= 0).all() and (g < s.shape[0]).all(), "invalid scale/group indices")
    k, n = len(g), a.shape[1]
    # Primary implementation: direct row/column nibble indexing, chunked rows.
    columns = np.arange(n)
    zeros = (((z[:, columns // 8] >> ((columns % 8) * 4).astype(np.uint32)) & 15) + 1).astype(np.float32)
    output = np.empty((k, n), dtype=np.float16)
    for begin in range(0, k, 64):
        rows = np.arange(begin, min(begin + 64, k))
        q = ((a[rows // 8] >> ((rows % 8) * 4).astype(np.uint32)[:, None]) & 15).astype(np.float32)
        output[begin:begin + len(rows)] = ((q - zeros[g[rows]]) * s[g[rows]].astype(np.float32)).astype(np.float16)
    require(np.isfinite(output).all(), "nonfinite decoded weight")
    return output


def independent_decode(qweight, qzeros, scales, g_idx):
    # Independent unpack traversal: interleave complete nibble planes.
    a = np.asarray(qweight, dtype=np.int32).view(np.uint32)
    z = np.asarray(qzeros, dtype=np.int32).view(np.uint32)
    s = np.asarray(scales, dtype=np.float16)
    g = np.asarray(g_idx, dtype=np.int64)
    q = np.stack([((a >> (4 * j)) & 15) for j in range(8)], axis=1).reshape(a.shape[0] * 8, a.shape[1])
    zeros = np.stack([((z >> (4 * j)) & 15) + 1 for j in range(8)], axis=2).reshape(z.shape[0], -1)[:, :s.shape[1]]
    result = ((q.astype(np.float32) - zeros[g].astype(np.float32)) * s[g].astype(np.float32)).astype(np.float16)
    require(np.isfinite(result).all(), "nonfinite independent decode")
    return result
