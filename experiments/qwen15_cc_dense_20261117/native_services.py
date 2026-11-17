"""Extract serial service boundaries for the frozen layer before applying OPPs."""

import hashlib
import json
from collections import Counter
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(contract_path, profiles_path, output):
    contract = read(contract_path)
    source = Path(contract['source'])
    for name, expected in contract['source_sha256'].items():
        assert sha(source / name) == expected, name
    numeric_path, rpc_path = (source / name for name in ('NUMERIC_CALLS.json', 'RPC_EVENTS.json'))
    lowering_path = source / 'backend/LOWERING.jsonl'
    numeric = read(numeric_path)
    rpc = read(rpc_path)
    profiles = read(profiles_path)['profiles']
    profiled_ops = {json.loads(key)[0] for key in profiles}
    matrix_by_handle = {row['FP32_result_handle']: row for row in numeric}
    lowering = [json.loads(line) for line in lowering_path.read_text().splitlines()]
    bound = set()
    segments = []
    cursor = contract['route']['router_done']
    for index, flow in enumerate(contract['transport']):
        end = flow['start']
        assert cursor <= end
        pieces = []
        for row in rpc:
            if row['opcode'] != 5 or not cursor <= row['start'] < end:
                continue
            activation, weight, result, m, n, k, f16 = row['arguments']
            call = matrix_by_handle[result]
            assert result not in bound and weight == call['expanded_weight_handle']
            assert f16 and call['MKN'] == [m, k, n]
            assert call['start'] <= row['start'] <= row['complete'] <= min(call['complete'], end)
            bound.add(result)
            op = f'moe_weight_mm_{m}_{k}_{n}'
            lowered = [event for event in lowering if (event['M'], event['K'], event['N']) == (m, k, n)
                       and row['start'] <= event['begin'] <= event['complete'] <= row['complete']]
            assert len(lowered) == 1, (row['sequence'], lowered)
            pieces.append(dict(kind='native_matrix_rpc', start=row['start'], done=row['complete'],
                               rpc_sequence=row['sequence'], output_handle=result, partition=call['partition'],
                               mkn=[m, k, n], label=call['label'], profile_shape_present=op in profiled_ops,
                               native_lowering=lowered[0]))
        events = []
        covered = cursor
        for piece in pieces:
            assert covered <= piece['start']
            if covered < piece['start']:
                events.append(dict(kind='other_serial_service', start=covered, done=piece['start']))
            events.append(piece)
            covered = piece['done']
        if covered < end:
            events.append(dict(kind='other_serial_service', start=covered, done=end))
        assert sum(p['done'] - p['start'] for p in events) == end - cursor
        segments.append(dict(before_transport=index, start=cursor, done=end, events=events))
        cursor = flow['complete']
    matrices = [event for segment in segments for event in segment['events']
                if event['kind'] == 'native_matrix_rpc']
    assert len(matrices) == len(bound) > 0
    counts = Counter(tuple(event['mkn']) for event in matrices)
    result = dict(status='BOUND_NATIVE_SERIAL_SERVICE_TIMELINE',
                  source_hashes={path.name: sha(path) for path in (numeric_path, rpc_path, lowering_path, contract_path)},
                  thermal_profile_hash=sha(profiles_path), matrices=len(matrices),
                  shape_counts=[dict(mkn=list(shape), calls=n) for shape, n in sorted(counts.items())],
                  matrices_with_same_profile_shape=sum(e['profile_shape_present'] for e in matrices),
                  segments=segments)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: val for key, val in result.items() if key != 'segments'}), flush=True)


if __name__ == '__main__':
    main(*(Path(arg) for arg in sys.argv[1:]))
