#!/usr/bin/env python3
"""Build an offline phase-2 memory timing analysis from PopNet and LPDDR5 traces.

This is benchmark-neutral: given one phase-2 PopNet ``delayInfo.txt``, the
NPU request-id transaction CSVs, and a DRAM service CSV, it produces a
request-id profile and helper CSVs for analysis.  The generated profile is
for inspection only; LPDDR5 timing belongs to Ramulator2 and the global
LEGOSIM timeline, while NPUSim reports its local on-chip schedule.
"""

from __future__ import annotations

import argparse
import csv
import glob
import pathlib
import sys
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Set, Tuple


@dataclass(frozen=True)
class Transaction:
    request_id: int
    operation: str
    label: str
    address: int
    bytes: int
    issue_cycle: int
    phase1_elapsed: int


@dataclass(frozen=True)
class DramService:
    request_id: int
    operation: str
    completion_cycles: int


@dataclass(frozen=True)
class PacketDelay:
    request_id: int
    injection_cycle: int
    source: Tuple[int, ...]
    destination: Tuple[int, ...]
    receiver_cycles: int


def positive_int(text: str) -> int:
    value = int(text, 0)
    if value < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return value


def expand_paths(patterns: Sequence[str]) -> List[pathlib.Path]:
    paths: List[pathlib.Path] = []
    for pattern in patterns:
        matched = [pathlib.Path(path) for path in glob.glob(pattern)]
        paths.extend(matched if matched else [pathlib.Path(pattern)])
    unique = sorted(set(paths))
    missing = [str(path) for path in unique if not path.is_file()]
    if missing:
        raise ValueError("missing input file(s): " + ", ".join(missing))
    return unique


def load_transactions(paths: Iterable[pathlib.Path]) -> Dict[int, Transaction]:
    transactions: Dict[int, Transaction] = {}
    required = {
        "request_id", "operation", "label", "address", "bytes", "issue_cycle",
        "phase1_elapsed_cycles",
    }
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ValueError(f"{path}: unexpected NPU transaction trace header")
            for row in reader:
                request_id = int(row["request_id"], 0)
                transaction = Transaction(
                    request_id=request_id,
                    operation=row["operation"],
                    label=row["label"],
                    address=int(row["address"], 0),
                    bytes=int(row["bytes"], 0),
                    issue_cycle=int(row["issue_cycle"], 0),
                    phase1_elapsed=int(row["phase1_elapsed_cycles"], 0),
                )
                if request_id in transactions:
                    raise ValueError(f"duplicate request_id {request_id} in NPU transaction traces")
                transactions[request_id] = transaction
    if not transactions:
        raise ValueError("NPU transaction traces contain no LOAD/STORE records")
    return transactions


def load_dram_service(path: pathlib.Path) -> Dict[int, DramService]:
    services: Dict[int, DramService] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"request_id", "operation", "service_cycles"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"{path}: unexpected DRAM timing trace header")
        for row in reader:
            request_id = int(row["request_id"], 0)
            cycles = row["queue_and_service_cycles"] if "queue_and_service_cycles" in row else row["service_cycles"]
            service = DramService(request_id, row["operation"], int(cycles, 0))
            if request_id in services:
                raise ValueError(f"duplicate request_id {request_id} in DRAM timing trace")
            services[request_id] = service
    return services


def parse_delay_line(path: pathlib.Path, line_no: int, line: str) -> PacketDelay:
    words = line.split()
    if len(words) < 6:
        raise ValueError(f"{path}:{line_no}: too few delayInfo fields")
    try:
        values = [int(word, 0) for word in words]
    except ValueError as exc:
        raise ValueError(f"{path}:{line_no}: delayInfo must contain integers") from exc

    # PopNet: <time> <src address...> <dst address...> <descriptor>
    #         <delay_count> <send_delay> <receive_delay> [...]
    # Enumerate valid layouts.  Searching backward is wrong when sender delay
    # is itself 1: it can be misidentified as delay_count.
    candidates = []
    for dimension in range(1, (len(values) - 3) // 2 + 1):
        delay_count_index = 2 * dimension + 2
        if delay_count_index >= len(values):
            continue
        delay_count = values[delay_count_index]
        if delay_count >= 1 and delay_count_index + 1 + delay_count == len(values):
            candidates.append((dimension, delay_count_index))
    if len(candidates) != 1:
        layouts = ", ".join(str(dimension) for dimension, _ in candidates) or "none"
        raise ValueError(f"{path}:{line_no}: ambiguous or malformed delayInfo layout "
                         f"(candidate address dimensions: {layouts})")
    dimension, delay_count_index = candidates[0]
    delays = values[delay_count_index + 1:]
    return PacketDelay(
        request_id=values[delay_count_index - 1],
        injection_cycle=values[0],
        source=tuple(values[1:1 + dimension]),
        destination=tuple(values[1 + dimension:1 + 2 * dimension]),
        receiver_cycles=delays[1] if len(delays) >= 2 else delays[0],
    )


def load_packet_delays(path: pathlib.Path, request_ids: Set[int]) -> Dict[int, List[PacketDelay]]:
    packets = {request_id: [] for request_id in request_ids}
    with path.open(encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            packet = parse_delay_line(path, line_no, line)
            if packet.request_id in packets:
                packets[packet.request_id].append(packet)
    return packets


def dram_address(args: argparse.Namespace, dimension: int) -> Tuple[int, ...]:
    if args.dram_address:
        values = tuple(int(value, 0) for value in args.dram_address.split(","))
        if len(values) != dimension:
            raise ValueError(f"--dram-address has {len(values)} dimensions, but delayInfo uses {dimension}")
        return values
    if dimension != 1:
        raise ValueError("2-D/ND delayInfo requires --dram-address, for example 5,4")
    return (args.dram_x + args.dram_y * args.mesh_width,)


def split_network_delay(transaction: Transaction,
                        record_packets: Sequence[PacketDelay],
                        destination: Tuple[int, ...]) -> Tuple[int, int]:
    request_packets = [packet for packet in record_packets if packet.destination == destination]
    response_packets = [packet for packet in record_packets if packet.source == destination]
    if not request_packets or not response_packets:
        raise ValueError(f"request_id {transaction.request_id}: missing DRAM-bound request or response packet; "
                         f"expected DRAM address {destination}, saw "
                         f"{[(packet.source, packet.destination) for packet in record_packets]}")
    request_complete = max(packet.injection_cycle + packet.receiver_cycles for packet in request_packets)
    request_network = max(0, request_complete - transaction.issue_cycle)
    response_network = max(packet.receiver_cycles for packet in response_packets)
    return request_network, response_network


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay", required=True, type=pathlib.Path)
    parser.add_argument("--transactions", required=True, nargs="+",
                        help="NPU transaction CSV path(s) or glob(s)")
    parser.add_argument("--dram-trace", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--detail-out", type=pathlib.Path)
    parser.add_argument("--arrival-out", type=pathlib.Path,
                        help="phase-2 arrival CSV for LPDDR5 timing analysis")
    parser.add_argument("--dram-x", type=positive_int, default=5)
    parser.add_argument("--dram-y", type=positive_int, default=4)
    parser.add_argument("--mesh-width", type=positive_int, default=6)
    parser.add_argument("--dram-address",
                        help="comma-separated PopNet DRAM coordinate; overrides x/y/width")
    args = parser.parse_args()

    if not args.delay.is_file():
        raise ValueError(f"missing PopNet delayInfo: {args.delay}")
    if not args.dram_trace.is_file():
        raise ValueError(f"missing DRAM timing trace: {args.dram_trace}")
    transactions = load_transactions(expand_paths(args.transactions))
    services = load_dram_service(args.dram_trace)
    packets = load_packet_delays(args.delay, set(transactions))
    detail_out = args.detail_out or args.out.with_suffix(".csv")
    for path in (args.out, detail_out, args.arrival_out):
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    arrivals = []
    for request_id in sorted(transactions):
        transaction = transactions[request_id]
        service = services.get(request_id)
        if service is None:
            raise ValueError(f"request_id {request_id}: no DRAM service record")
        if service.operation != transaction.operation:
            raise ValueError(f"request_id {request_id}: NPU/DRAM operation mismatch")
        record_packets = packets[request_id]
        if not record_packets:
            raise ValueError(f"request_id {request_id}: no matching PopNet delayInfo record")
        request_network, response_network = split_network_delay(
            transaction, record_packets, dram_address(args, len(record_packets[0].source)))
        end_to_end = request_network + service.completion_cycles + response_network
        rows.append((request_id, transaction.operation, request_network, service.completion_cycles,
                     response_network, end_to_end, transaction.label, transaction.issue_cycle,
                     transaction.phase1_elapsed, len(record_packets)))
        arrivals.append((request_id, transaction.operation, transaction.address, transaction.bytes,
                         transaction.issue_cycle + request_network, response_network))

    with args.out.open("w", encoding="utf-8", newline="") as handle:
        handle.write("# NPUSim request-id memory timing profile\n")
        handle.write("# request_id operation request_network_cycles dram_queue_and_service_cycles "
                     "response_network_cycles end_to_end_cycles\n")
        for row in rows:
            handle.write("{} {} {} {} {} {}\n".format(*row[:6]))
    with detail_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["request_id", "operation", "request_network_cycles", "dram_service_cycles",
                         "response_network_cycles", "end_to_end_cycles", "label", "issue_cycle",
                         "phase1_elapsed_cycles", "popnet_packet_count"])
        writer.writerows(rows)
    if args.arrival_out:
        with args.arrival_out.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["request_id", "operation", "address", "bytes",
                             "request_arrival_cycle", "response_network_cycles"])
            writer.writerows(arrivals)
    print("[NPUSIM-PROFILE] requests={} profile={} details={}{}".format(
        len(rows), args.out, detail_out,
        " arrivals=" + str(args.arrival_out) if args.arrival_out else ""))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"[NPUSIM-FEEDBACK][ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
