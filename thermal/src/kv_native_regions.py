"""Task-aware physical Qwen K/V wave regions on the fixed V3.5 DRAM map.

K prefill is stored head-major and transposed for QK. Its one decode token
occupies a contiguous tail. V is token-major. Both layouts fit in one
request-isolated, 8-KiB-aligned slot per head. This is a declared MODELED
tensor layout, not a checkpoint memory trace.
"""
import sys
from pathlib import Path


PARENT = Path(__file__).resolve().parent.parent / "sustained_thermal_v35_20260914"
sys.path.insert(0, str(PARENT))
from backend import Memory  # noqa: E402


HEAD_WIDTH = 128
PREFILL_TOKENS = 512
MAX_TOKENS = 513
BYTES = 2


def wave_regions(task, plan, wave, write, partition_bytes, weight_base,
                 workspace_base, address_book, include_b=True):
    """Return the native key and physical segments, preserving useful bytes."""
    key, original = Memory.wave_regions(
        task["shape"], plan, wave, write, partition_bytes,
        weight_base, workspace_base, include_b)
    role = task.get("kv_native_role")
    if not role or (write != role.startswith("write_")):
        return key, original
    assert int(task["layer"]) >= 0
    assert task["stage"] in ("prefill", "decode")
    assert plan["m"] == (PREFILL_TOKENS if task["stage"] == "prefill" else 1)
    head = int(task.get("kv_head", wave["nj"] // HEAD_WIDTH))
    local_col = (wave["nj"] if "kv_head" in task else
                 wave["nj"] % HEAD_WIDTH) if write else 0
    assert 0 <= head < 16
    kind = role[-1]
    assert kind in ("k", "v")
    entry = address_book[f'l{task["layer"]}:kv:{kind}:h{head}']
    assert entry["partition"] == int(task["primary_cluster"])
    stride = int(entry["request_slot_stride_bytes"])
    slots = int(entry["size_bytes"]) // stride
    request_slot = int(task.get("kv_request_slot", 0))
    assert 0 <= request_slot < slots
    base = int(entry["base_address"]) + request_slot*stride
    segments = []
    if role.startswith("write_"):
        assert wave["kk"] + wave["kt"] == plan["k"]
        assert 0 <= local_col and local_col + wave["nt"] <= HEAD_WIDTH
        if task["stage"] == "prefill" and kind == "k":
            # Native output C tile [token, dim] is written as [dim, token].
            for dim in range(local_col, local_col + wave["nt"]):
                segments.append((base + BYTES * (dim * PREFILL_TOKENS + wave["mi"]),
                                 BYTES * wave["mt"]))
        elif task["stage"] == "prefill" and kind == "v":
            if local_col == 0 and wave["nt"] == HEAD_WIDTH:
                segments.append((base + BYTES * wave["mi"] * HEAD_WIDTH,
                                 BYTES * wave["mt"] * HEAD_WIDTH))
            else:
                for token in range(wave["mi"], wave["mi"] + wave["mt"]):
                    segments.append((base + BYTES * (token * HEAD_WIDTH + local_col),
                                     BYTES * wave["nt"]))
        else:
            assert wave["mi"] == 0 and wave["mt"] == 1
            segments.append((base + BYTES *
                             (PREFILL_TOKENS * HEAD_WIDTH + local_col),
                             BYTES * wave["nt"]))
        assert sum(size for _, size in segments) == BYTES * wave["mt"] * wave["nt"]
    else:
        # The native A operand stays in transient workspace. Only the B
        # operand is redirected to the cache owning this head.
        assert include_b
        a_segments = (1 if wave["kt"] == plan["k"] else wave["mt"])
        segments.extend(original[:a_segments])
        if kind == "k":
            assert plan["k"] == HEAD_WIDTH
            if wave["nj"] < PREFILL_TOKENS:
                assert wave["nj"] + wave["nt"] <= PREFILL_TOKENS
                for dim in range(wave["kk"], wave["kk"] + wave["kt"]):
                    segments.append((base + BYTES *
                                     (dim * PREFILL_TOKENS + wave["nj"]),
                                     BYTES * wave["nt"]))
            else:
                assert wave["nj"] == PREFILL_TOKENS and wave["nt"] == 1
                segments.append((base + BYTES *
                                 (PREFILL_TOKENS * HEAD_WIDTH + wave["kk"]),
                                 BYTES * wave["kt"]))
        else:
            assert plan["n"] == HEAD_WIDTH
            if wave["nj"] == 0 and wave["nt"] == HEAD_WIDTH:
                segments.append((base + BYTES * wave["kk"] * HEAD_WIDTH,
                                 BYTES * wave["kt"] * HEAD_WIDTH))
            else:
                for token in range(wave["kk"], wave["kk"] + wave["kt"]):
                    segments.append((base + BYTES *
                                     (token * HEAD_WIDTH + wave["nj"]),
                                     BYTES * wave["nt"]))
        assert sum(size for _, size in segments) == sum(size for _, size in original)
    assert all(base <= addr and addr + size <= base + stride
               for addr, size in segments[(0 if write else a_segments):])
    return tuple(key) + ("physical_kv", role, head, base % 8192), segments
