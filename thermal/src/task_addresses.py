"""Resolve address-audited MoE task operands within the fixed V3.5 partitions."""


def task_address(task, policy, addresses, capacity, cluster, side):
    if side not in ("read", "write"):
        raise ValueError(side)
    workspace = capacity[policy][cluster]["scratch_base_address"]
    key = task.get(f"{side}_address_key")
    if key is not None:
        entry = addresses[policy][key]
        assert entry["partition"] == cluster, (policy, key, cluster)
        offset = task.get(f"{side}_offset", 0)
        size = task[f"{side}_bytes"]
        assert 0 <= offset and offset + size <= entry["request_slot_stride_bytes"]
        return entry["base_address"] + offset
    address = workspace + task.get(f"{side}_workspace_offset", 0)
    size = task[f"{side}_bytes"]
    assert size <= capacity[policy][cluster]["scratch_reserve_bytes"]
    assert address + size <= workspace + capacity[policy][cluster]["scratch_reserve_bytes"]
    return address
