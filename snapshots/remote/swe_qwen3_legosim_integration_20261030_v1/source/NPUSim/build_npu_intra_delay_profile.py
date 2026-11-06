#!/usr/bin/env python3
"""Build an NPU intra-array delay profile from a PopNet delayInfo file."""

import argparse
import json
import os


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", default="delayInfo_npu_intra.txt")
    parser.add_argument("--out", default="reports/npu_intra_delay_profile.txt")
    parser.add_argument("--mac-count", type=int, default=16)
    parser.add_argument("--config", default="npu_config.json")
    return parser.parse_args()


def to_int(token):
    try:
        return int(token)
    except Exception:
        return int(round(float(token)))


def load_delay_records(path):
    records = []
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            try:
                cycle = to_int(parts[0])
                src = to_int(parts[1])
                dst = to_int(parts[2])
                desc = to_int(parts[3])
                delay_count = max(0, to_int(parts[4]))
            except Exception:
                continue
            if len(parts) < 5 + delay_count:
                continue
            delays = []
            for idx in range(delay_count):
                try:
                    delays.append(to_int(parts[5 + idx]))
                except Exception:
                    delays = []
                    break
            if delays:
                records.append((cycle, src, dst, desc, delays))
    return records


def load_topology_config(path, mac_count):
    if not path or not os.path.exists(path):
        raise SystemExit(f"[npu-delay] ERROR: config file not found: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        root = json.load(handle)
    npu = root.get("npu", {})
    topo = npu.get("topology", {})
    mac_count = int(npu.get("mac_unit_count", mac_count))
    if "mac_nodes" not in topo:
        raise SystemExit("[npu-delay] ERROR: config must provide npu.topology.mac_nodes")
    mac_nodes = [int(x) for x in topo.get("mac_nodes", [])]
    if len(mac_nodes) != mac_count:
        raise SystemExit(
            f"[npu-delay] ERROR: mac_nodes has {len(mac_nodes)} entries, mac_unit_count is {mac_count}"
        )
    if "controller_node" not in topo and "controller_local_id" not in topo:
        raise SystemExit("[npu-delay] ERROR: config must provide npu.topology.controller_node")
    controller_id = int(topo.get("controller_node", topo.get("controller_local_id")))
    node_count = int(topo.get("node_count", max([controller_id] + mac_nodes) + 1))
    return mac_nodes, controller_id, node_count


def build_profile(records, mac_nodes, controller_id):
    mac_count = max(1, len(mac_nodes))
    node_to_mac = {int(node): idx for idx, node in enumerate(mac_nodes)}
    per_src = [0 for _ in range(mac_count)]
    per_dst = [0 for _ in range(mac_count)]
    packet_count = 0
    total_src = 0
    total_dst = 0
    per_task = {}

    for _, src, dst, desc, delays in records:
        src_delay = int(delays[0]) if delays else 0
        dst_delay = int(delays[1]) if len(delays) >= 2 else src_delay
        if desc != 0:
            item = per_task.setdefault(
                int(desc),
                {
                    "dst": 0,
                    "src": 0,
                    "ingress_dst": 0,
                    "egress_dst": 0,
                    "internal_dst": 0,
                    "ingress_src": 0,
                    "egress_src": 0,
                    "internal_src": 0,
                    "packets": 0,
                },
            )
            # Packets in one direction are concurrent.  The controller-centric
            # task pays the slowest ingress route plus the slowest egress
            # route, rather than the sum of all packet delays.
            if src == controller_id:
                item["ingress_src"] = max(item["ingress_src"], max(0, src_delay))
                item["ingress_dst"] = max(item["ingress_dst"], max(0, dst_delay))
            elif dst == controller_id:
                item["egress_src"] = max(item["egress_src"], max(0, src_delay))
                item["egress_dst"] = max(item["egress_dst"], max(0, dst_delay))
            else:
                item["internal_src"] = max(item["internal_src"], max(0, src_delay))
                item["internal_dst"] = max(item["internal_dst"], max(0, dst_delay))
            item["src"] = (
                item["ingress_src"] + item["egress_src"] + item["internal_src"]
            )
            item["dst"] = (
                item["ingress_dst"] + item["egress_dst"] + item["internal_dst"]
            )
            item["packets"] += 1
        if src == controller_id or dst == controller_id:
            if src in node_to_mac:
                per_src[node_to_mac[src]] = max(per_src[node_to_mac[src]], max(0, src_delay))
            if dst in node_to_mac:
                per_dst[node_to_mac[dst]] = max(per_dst[node_to_mac[dst]], max(0, dst_delay))
            packet_count += 1
            item = per_task.get(int(desc))
            if item is not None:
                total_src = max(total_src, item["src"])
                total_dst = max(total_dst, item["dst"])
            continue
        if src not in node_to_mac and dst not in node_to_mac:
            continue
        if src in node_to_mac:
            per_src[node_to_mac[src]] = max(per_src[node_to_mac[src]], max(0, src_delay))
        if dst in node_to_mac:
            per_dst[node_to_mac[dst]] = max(per_dst[node_to_mac[dst]], max(0, dst_delay))
        item = per_task.get(int(desc))
        if item is not None:
            total_src = max(total_src, item["src"])
            total_dst = max(total_dst, item["dst"])
        packet_count += 1

    return {
        "mac_count": mac_count,
        "controller_id": controller_id,
        "mac_nodes": mac_nodes,
        "packet_count": packet_count,
        "total_src_delay": total_src,
        "total_dst_delay": total_dst,
        "per_src_delay": per_src,
        "per_dst_delay": per_dst,
        "per_task": per_task,
    }


def write_profile(path, profile):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# NPU intra delay profile generated from PopNet delayInfo\n")
        handle.write("# format:\n")
        handle.write("#   TOTAL <dst_delay_cycles>\n")
        handle.write("#   PACKETS <count>\n")
        handle.write("#   TASK <desc> <dst_delay_cycles> <src_delay_cycles> <packet_count>\n")
        handle.write("#   MAC <id> <dst_delay_cycles> <src_delay_cycles>\n")
        handle.write(f"META mac_count {profile['mac_count']}\n")
        handle.write(f"META controller_id {profile['controller_id']}\n")
        handle.write("META mac_nodes " + ",".join(str(x) for x in profile["mac_nodes"]) + "\n")
        handle.write(f"TOTAL {profile['total_dst_delay']}\n")
        handle.write(f"PACKETS {profile['packet_count']}\n")
        for desc in sorted(profile["per_task"]):
            item = profile["per_task"][desc]
            handle.write(f"TASK {desc} {item['dst']} {item['src']} {item['packets']}\n")
        for mac_id in range(profile["mac_count"]):
            handle.write(
                f"MAC {mac_id} {profile['per_dst_delay'][mac_id]} {profile['per_src_delay'][mac_id]}\n"
            )


def main():
    args = parse_args()
    if not os.path.exists(args.delay):
        raise SystemExit(f"[npu-delay] ERROR: delay file not found: {args.delay}")
    mac_nodes, controller_id, _ = load_topology_config(args.config, args.mac_count)
    records = load_delay_records(args.delay)
    profile = build_profile(records, mac_nodes, controller_id)
    write_profile(args.out, profile)
    print(f"[npu-delay] input: {args.delay}")
    print(f"[npu-delay] packets: {profile['packet_count']}")
    print(f"[npu-delay] total_dst_delay: {profile['total_dst_delay']}")
    print(f"[npu-delay] output: {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
