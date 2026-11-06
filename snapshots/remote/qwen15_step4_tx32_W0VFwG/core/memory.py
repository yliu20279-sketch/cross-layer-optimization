"""Exact byte and lifetime contracts; does not simulate paging or memory cost."""
from dataclasses import dataclass
from .common import nonnegative_time, require

DTYPE_BYTES = {"BF16": 2, "F16": 2, "F32": 4, "I32": 4, "U8": 1}


def tensor_bytes(shape, dtype):
    require(dtype in DTYPE_BYTES and bool(shape), "unsupported tensor dtype/shape")
    count = 1
    for dim in shape:
        require(isinstance(dim, int) and dim > 0, "invalid tensor dimension")
        count *= dim
    return count * DTYPE_BYTES[dtype]


def split_pages(address, size, page_bytes=4096):
    require(isinstance(address, int) and address >= 0 and isinstance(size, int) and size > 0,
            "invalid memory extent")
    require(page_bytes > 0, "invalid page size")
    chunks = []
    while size:
        n = min(size, page_bytes - address % page_bytes)
        chunks.append((address // page_bytes, address % page_bytes, n))
        address += n
        size -= n
    return chunks


@dataclass(frozen=True)
class Residency:
    identity: str
    partition: int
    address: int
    bytes: int
    start: float
    done: float


def check_residency(objects, capacities):
    require(bool(objects) and bool(capacities), "residency evidence required")
    seen = set()
    for obj in objects:
        nonnegative_time(obj.start)
        nonnegative_time(obj.done)
        require(obj.done > obj.start, "empty/negative residency")
        require(obj.identity not in seen, "duplicate allocation version")
        seen.add(obj.identity)
        require(obj.partition in capacities and obj.address >= 0 and obj.bytes > 0,
                "invalid allocation")
        require(obj.address + obj.bytes <= capacities[obj.partition], "capacity overflow")
    for i, left in enumerate(objects):
        for right in objects[i + 1:]:
            if left.partition != right.partition:
                continue
            temporal = max(left.start, right.start) < min(left.done, right.done)
            spatial = max(left.address, right.address) < min(left.address + left.bytes,
                                                             right.address + right.bytes)
            require(not (temporal and spatial), "live allocations alias")
    peaks = {}
    for part in capacities:
        changes = [(t, delta) for obj in objects if obj.partition == part
                   for t, delta in ((obj.start, obj.bytes), (obj.done, -obj.bytes))]
        live = peak = 0
        for _, delta in sorted(changes):
            live += delta
            require(0 <= live <= capacities[part], "lifetime capacity invalid")
            peak = max(peak, live)
        require(live == 0, "unreleased residency")
        peaks[part] = peak
    return peaks


def validate_mapping(base, candidate, pages, decoder):
    """Decoder is an explicit backend-provenance binding, never inferred here."""
    backend = decoder.get("backend_sha256", "")
    require(isinstance(backend, str) and len(backend) == 64 and
            all(c in "0123456789abcdef" for c in backend) and decoder.get("address_unit") == "frame4096",
            "bound backend decoder required")
    require(set(base) == set(candidate) == set(pages), "mapping page domain changed")
    require(all(isinstance(v, int) and v >= 0 for v in candidate.values()), "invalid frame")
    for partition in sorted({p["partition"] for p in pages.values()}):
        keys = [key for key, p in pages.items() if p["partition"] == partition]
        old, new = [base[k] for k in keys], [candidate[k] for k in keys]
        require(len(set(old)) == len(old) and len(set(new)) == len(new), "frame alias")
        require(set(old) == set(new), "partition frame pool changed")
        for key in keys:
            page = pages[key]
            require(page.get("bytes", 0) > 0 and page["bytes"] <= 4096, "invalid page payload")
            if not page.get("movable", False):
                require(candidate[key] == base[key], "fixed object moved")
            banks = decoder.get("frame_banks", {}).get(str(partition), {})
            require(str(candidate[key]) in banks, "frame lacks bound decoder result")
            require(isinstance(banks[str(candidate[key])], int) and 0 <= banks[str(candidate[key])] < 16,
                    "invalid decoded Bank")
    return True
