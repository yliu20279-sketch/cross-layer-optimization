"""Freeze and replay dense GetS arrivals with the Qwen1.5 HiBand reference."""

from collections import defaultdict
import csv
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys


SOURCE = Path('/mnt/sda1/h3240101068/qwen15_step4_tx32_W0VFwG/runs/qwen15_pp56rmsfixed')
ROOT = Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO')
SUITE = ROOT / 'benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006'
BINARY = SUITE / 'popnet_coupled_src/build_coupled/popnet'
RAM = ROOT / 'benchmark/qwen1_5_moe_a2_7b_v3_6/target_architecture_v3_6/ramulator2_hb_partition_v3_6_execution_overlay.yaml'
BINARY_HASH = '9d437a1cd913a71cb767e45a4a0394f49275a97a02276bce37f397d9f0e89ff7'
STAGES = {'dispatch', 'combine', 'shared_input', 'shared_reduce', 'SAG'}
MODES = [('FULL_LOCAL', 1536, 0), ('LOCAL_BIAS', 1024, 512),
         ('GLOBAL_BIAS', 512, 1024), ('FULL_GLOBAL', 0, 1536)]
FLIT_BYTES = 32
MOE_READY = 32
REQUEST_START = 0
CASES = {'combined_overload': 2, 'matched': 1}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def table(path, fields, values):
    with path.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        writer.writerows(values)


def rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def freeze_inputs(source_contract, output):
    source = load(source_contract)
    dispatch = source['transport'][0]
    assert (dispatch['stage'], dispatch['src'], dispatch['dst']) == ('dispatch', 0, 1)
    assert dispatch['bytes'] % FLIT_BYTES == 0
    moe_flits = dispatch['bytes'] // FLIT_BYTES
    # Nominal one-flit/cycle serializer. The reference packet tail may take extra cycles.
    window_end = MOE_READY + moe_flits
    end = REQUEST_START + 4 * moe_flits
    for case, period in CASES.items():
        transactions = [dict(id=i, arrival=tick, src=0, dst=1, request_bytes=32,
                             read_bytes=64, reply_bytes=64, address=0x10000000 + i * 64)
                        for i, tick in enumerate(range(REQUEST_START, end, period))]
        cc_flits = sum(MOE_READY <= t['arrival'] < window_end for t in transactions)
        save(output / f'{case}.json', dict(
            case=case, source_sha256=source['source_sha256'],
            shared_directed_port=[0, 1], flit_bytes=FLIT_BYTES, nominal_port_flits_per_cycle=1,
            arrival_interval_cycles=[REQUEST_START, end], nominal_overlap_cycles=[MOE_READY, window_end],
            moe_dispatch_flits=moe_flits, gets_request_flits_in_overlap=cc_flits,
            moe_offered_flits_per_cycle=1, gets_offered_flits_per_cycle=cc_flits / moe_flits,
            combined_offered_flits_per_cycle=(cc_flits + moe_flits) / moe_flits,
            transactions=transactions))


def prepare(run, arrivals):
    source_files = ('RESULT.json', 'TRANSPORT.json', 'PROTOCOL.json', 'prefill_L5_input.bin',
                    'prefill_L5_output.bin')
    phase = load(SOURCE / source_files[0])['phases'][0]
    assert (phase['layer'], phase['tokens'], phase['positions']) == (5, 1, [0])
    route, = phase['routes']
    assert len(set(route['selected'])) == 4
    assert phase['output_sha256'] == sha(SOURCE / source_files[4])
    transport = [event for event in load(SOURCE / source_files[1])
                 if route['router_done'] <= event['start'] < phase['complete']]
    assert len(transport) == 15 and {event['stage'] for event in transport} == STAGES
    assert transport[0]['stage'] == 'dispatch' and transport[-1]['complete'] == phase['complete']
    source_hashes = {name: sha(SOURCE / name) for name in source_files}
    assert source_hashes == arrivals['source_sha256']
    assert [transport[0]['src'], transport[0]['dst']] == arrivals['shared_directed_port']
    ops, deps = [], []

    def op(kind, name, pe=0, count=0, address=0, cycles=0, src=-1, dst=-1, parents=()):
        index = len(ops)
        sample = count if kind in ('LOAD', 'STORE') else 0
        ops.append((index, kind, name, 'COMPUTE' if kind == 'COMPUTE' else name,
                    pe, count, sample, address, cycles, src, dst, 'local', pe))
        deps.extend((parent, index) for parent in parents)
        return index

    moe = op('COMPUTE', 'moe_external_start_delay', pe=15, cycles=MOE_READY)
    previous = route['router_done']
    first_dispatch = None
    for index, event in enumerate(transport):
        source, dest = event['src'], event['dst']
        gap = event['start'] - previous
        assert gap >= 0 and 0 <= source < 4 and 0 <= dest < 4 and source != dest
        assert event['bytes'] == 4096 and event['target_noc']
        if gap:
            moe = op('COMPUTE', f'moe_frozen_service_{index}', pe=source, cycles=gap, parents=(moe,))
        label = f'moe_{event["stage"]}_{index}'
        message = op('NET', label, count=event['bytes'], src=source, dst=dest, parents=(moe,))
        if first_dispatch is None:
            first_dispatch = message
        moe = op('STORE', label + '_commit', pe=dest, count=event['bytes'],
                 address=0x08000000 + index * 4096, parents=(message,))
        previous = event['complete']

    gets = []
    previous_tick, previous_release = 0, None
    for txn in arrivals['transactions']:
        index, tick = txn['id'], txn['arrival']
        src, dst = txn['src'], txn['dst']
        assert [src, dst] == arrivals['shared_directed_port'] and tick >= previous_tick
        # Only the previous timer is a predecessor. Traffic backpressure cannot delay arrivals.
        release = op('COMPUTE', f'cc_release_{index}', pe=14, cycles=tick - previous_tick,
                     parents=() if previous_release is None else (previous_release,))
        request = op('NET', f'gets_{index}', count=txn['request_bytes'], src=src, dst=dst, parents=(release,))
        memory = op('LOAD', f'gets_bank_{index}', pe=dst, count=txn['read_bytes'],
                    address=txn['address'], parents=(request,))
        response = op('NET', f'gets_data_{index}', count=txn['reply_bytes'], src=dst, dst=src, parents=(memory,))
        gets.append(dict(release=release, request=request, bank=memory, response=response, arrival=tick))
        previous_tick, previous_release = tick, release
    finish = op('BARRIER', 'mixed_join', parents=(moe, *(event['response'] for event in gets)))

    graph = run / 'graph'
    graph.mkdir()
    table(graph / 'ops.csv', 'id kind task phase pe bytes sample_bytes address cycles src dst scope rank'.split(), ops)
    table(graph / 'deps.csv', ('src', 'dst'), deps)
    table(graph / 'modes.csv', ('mode', 'local_bytes_per_cycle', 'global_bytes_per_cycle'), MODES)
    contract = dict(scope='Qwen1.5 layer 5 MoE suffix replay from recorded router completion',
                    source=str(SOURCE), source_sha256=source_hashes,
                    route=route, transport=transport, precision='F16 with K64 FP32 partials in source',
                    role='local HiBand reference density run, modeled GetS with a DRAM completion dependency',
                    common_arrival=0, gets=gets, first_dispatch=first_dispatch, moe_done=moe, join=finish)
    save(run / 'CONTRACT.json', contract)
    return contract


def audit(run, contract, arrivals):
    model = load(run / 'run_manifest.json')
    events = {int(event['id']): event for event in rows(run / 'events.csv')}
    mode = rows(run / 'mode_changes.csv')
    assert model['status'] == 'PASS' and model['causal_violations'] == 0
    assert model['packets_injected'] == model['packets_completed'] == 60 + 2 * len(contract['gets'])
    assert model['represented_remote_noc_bytes'] == sum(e['bytes'] for e in contract['transport']) + sum(
        txn['request_bytes'] + txn['reply_bytes'] for txn in arrivals['transactions'])
    assert mode and {row['mode'] for row in mode} == {'FULL_LOCAL'}

    def at(index, field):
        return float(events[index][field])

    packets = defaultdict(list)
    for packet in rows(run / 'packet_completions.csv'):
        packets[int(packet['op_id'])].append(packet)
    bank_log = defaultdict(list)
    for access in rows(run / 'bank_requests.csv'):
        bank_log[int(access['op_id'])].append(access)

    receipt = []
    for cc, txn in zip(contract['gets'], arrivals['transactions']):
        req, bank, rsp = (cc[key] for key in ('request', 'bank', 'response'))
        release = at(req, 'ready')
        assert release == cc['arrival'] == at(cc['release'], 'done')
        assert at(req, 'done') <= at(bank, 'start') < at(bank, 'done') <= at(rsp, 'start')
        request_packet, = packets[req]
        assert len(packets[rsp]) == 1
        injection = float(request_packet['inject'])
        assert release <= injection <= at(req, 'done')
        records = bank_log[bank]
        assert sum(int(row['request_bytes']) for row in records) == txn['read_bytes']
        assert all(int(row['partition']) == txn['dst'] and float(row['callback_cycle']) <= at(bank, 'done')
                   for row in records)
        receipt.append(dict(id=txn['id'], arrival=release, request_injected=injection,
                            request_done=at(req, 'done'), bank_start=at(bank, 'start'),
                            bank_done=at(bank, 'done'), response_done=at(rsp, 'done')))
    first_dispatch = dict(start=at(contract['first_dispatch'], 'start'), done=at(contract['first_dispatch'], 'done'))
    cc_end = max(row['response_done'] for row in receipt)
    moe_end = at(contract['moe_done'], 'done')
    join = at(contract['join'], 'done')
    assert first_dispatch['start'] < cc_end and join == max(moe_end, cc_end) == model['total_cycles']
    a, b = arrivals['nominal_overlap_cycles']
    offered = sum(a <= r['arrival'] < b for r in receipt)
    assert offered == arrivals['gets_request_flits_in_overlap']
    table(run / 'gets_transactions.csv', list(receipt[0]), [list(r.values()) for r in receipt])
    return dict(status='PASS_LIMITED_HIBAND_REFERENCE_MOE_SUFFIX', first_dispatch=first_dispatch,
                case=arrivals['case'], nominal_overlap=[a, b], gets_transactions=len(receipt),
                gets_ready_in_nominal_overlap=offered,
                gets_injected_in_nominal_overlap=sum(a <= r['request_injected'] < b for r in receipt),
                mean_request_release_to_inject=statistics.mean(r['request_injected'] - r['arrival'] for r in receipt),
                max_gets_response_latency=max(r['response_done'] - r['arrival'] for r in receipt),
                last_response=cc_end, moe_done=moe_end, mixed_join=join, modes=mode,
                packets=model['packets_completed'])


def main(run, arrival_file):
    assert sha(BINARY) == BINARY_HASH
    run.mkdir()
    print('RUN_DIR=' + str(run), flush=True)
    arrivals = load(arrival_file)
    (run / 'ARRIVALS.json').write_bytes(arrival_file.read_bytes())
    contract = prepare(run, arrivals)
    if not RAM.is_file():
        raise FileNotFoundError(RAM)
    (run / 'empty.trace').touch()
    controls = dict(POPNET_COUPLED='1', HB_GRAPH=str(run / 'graph'), HB_OUT=str(run),
                    POPNET_STATS_DIR=str(run), POPNET_STATS_WINDOW_CYCLES='100000',
                    HB_RAM_CONFIG=str(RAM), HB_ARCH_TX_BYTES='32', HB_BASE_BYTES_PER_CYCLE='25.6',
                    HB_NOC_SCALE='1', HB_SWITCH_COST='40')
    command = [str(BINARY), '-A', '4', '-c', '2', '-V', '2', '-B', '12', '-O', '12', '-F', '4',
               '-L', '1000', '-T', '1000000000', '-r', '1', '-I', str(run / 'empty.trace'), '-R', '0']
    environment = {key: val for key, val in os.environ.items() if not key.startswith(('HB_', 'POPNET_'))}
    save(run / 'LAUNCH.json', dict(command=command, controls=controls, binary_sha256=BINARY_HASH,
                                 ramulator_sha256=sha(RAM), code_sha256=sha(Path(__file__)),
                                 arrivals_sha256=sha(arrival_file),
                                 graph_sha256={p.name: sha(p) for p in (run / 'graph').glob('*.csv')}))
    with (run / 'stdout.log').open('w') as stream:
        subprocess.run(command, env={**environment, **controls}, cwd=run, stdout=stream,
                       stderr=subprocess.STDOUT, check=True, timeout=1800)
    result = audit(run, contract, arrivals)
    save(run / 'RECEIPT.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    operation, first, second = sys.argv[1:]
    if operation == 'freeze':
        freeze_inputs(Path(first), Path(second))
    elif operation == 'run':
        main(Path(first).resolve(), Path(second).resolve())
    else:
        raise ValueError(f'Unknown command {operation}')
