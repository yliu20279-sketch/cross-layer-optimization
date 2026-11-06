"""Deterministic control/reference ledger. No backend launch capability."""
from decimal import Decimal, ROUND_CEILING
from .common import nonnegative_time, require

MODES = {"FULL_LOCAL": (1536, 0), "LOCAL_BIAS": (1024, 512),
         "GLOBAL_BIAS": (512, 1024), "FULL_GLOBAL": (0, 1536)}
COSTS = ("cpu_services", "query", "installation", "migration", "cache_maintenance",
         "version_switch", "software_tables", "collectives", "paging", "sram")


def ns_to_ticks(ns, tick_ns):
    a, b = Decimal(str(ns)), Decimal(str(tick_ns))
    require(a.is_finite() and b.is_finite() and a >= 0 and b > 0, "invalid clock conversion")
    return int((a / b).to_integral_value(rounding=ROUND_CEILING))


def controls(scheme, transaction_bytes, pci_latency_ns):
    require(scheme in ("baseline_ep", "sem_moe", "hiband", "hiband_sem_moe"), "unknown scheme")
    require(transaction_bytes in (32, 256) and pci_latency_ns > 0, "invalid ABI")
    result = {"HB_ARCH_TX_BYTES": str(transaction_bytes), "HB_PCIE_LATENCY_NS": str(pci_latency_ns)}
    if scheme in ("baseline_ep", "sem_moe"):
        result["HB_FIXED_MODE"] = "GLOBAL_BIAS"
    return result


def sanitized_environment(scheme, transaction_bytes, pci_latency_ns):
    # No inherited environment. A future backend adapter must explicitly provide
    # its required, hashed ABI fields; this reference cannot launch a simulator.
    return controls(scheme, transaction_bytes, pci_latency_ns)


class ModeController:
    def __init__(self, switch_ticks):
        require(isinstance(switch_ticks, int) and switch_ticks >= 0, "switch cost required")
        self.switch_ticks = switch_ticks
        self.mode = "GLOBAL_BIAS"
        self.ready = 0

    def select(self, local_pending, global_pending, now, inflight):
        nonnegative_time(now)
        require(local_pending >= 0 and global_pending >= 0 and inflight >= 0, "negative queue")
        desired = "LOCAL_BIAS" if local_pending > global_pending else "GLOBAL_BIAS"
        old = self.mode
        # Both pools retain bandwidth, avoiding fixed FULL_* mixed-traffic stalls.
        if desired != self.mode and inflight == 0 and now >= self.ready:
            self.mode, self.ready = desired, now + self.switch_ticks
        require(sum(MODES[self.mode]) == 1536, "mode budget changed")
        return {"old": old, "mode": self.mode, "switch_ready": self.ready,
                "can_issue": now >= self.ready,
                "scope": "reference policy, not author HiBand scheduler"}


def aggregate_costs(ledger):
    """Only disjoint measured intervals in one target clock domain are additive."""
    missing = [name for name in COSTS if name not in ledger]
    require(not missing, "missing costs: " + ",".join(missing))
    domains, intervals = set(), []
    for name in COSTS:
        item = ledger[name]
        require(item.get("status") in ("measured", "not_applicable"), name + " unverified")
        require(item.get("evidence_sha256"), name + " missing evidence")
        if item["status"] == "not_applicable":
            require(item.get("reason"), "not-applicable cost needs a reason")
            continue
        require(item.get("clock_domain") and item.get("unit") == "target_ticks", "incompatible cost domain")
        domains.add(item["clock_domain"])
        for begin, end in item.get("exclusive_intervals", []):
            nonnegative_time(begin)
            nonnegative_time(end)
            require(end >= begin, "negative cost interval")
            intervals.append((begin, end))
        require(item.get("exclusive_intervals"), name + " lacks timed intervals")
    require(len(domains) <= 1, "mixed clock domains")
    for left, right in zip(sorted(intervals), sorted(intervals)[1:]):
        require(left[1] <= right[0], "overlapping costs cannot be summed")
    return sum(end - begin for begin, end in intervals)
