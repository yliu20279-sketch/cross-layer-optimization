"""Require full layer output, true cross-domain callbacks and matching payloads."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


ARMS = ('hiband_reference','project_noc')
METRICS = ('moe_communication_ns','moe_wire_latency_sum_ns','moe_ns','layer_ns')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def same_metadata(rows, keys):
    return [tuple(row[k] for k in keys) for row in rows]


def audit(root, tag, tokens):
    receipt = {}
    protocol = []
    routes = []
    payloads = []
    compute = []
    for arm in ARMS:
        run = root/f'{tag}_{arm}'
        spec = read(run/'PROTOCOL.json')
        result = read(run/'RESULT.json')
        traces = read(run/'TRANSPORT.json')
        messages = traces['events']
        assert result['status']=='PASS_MULTITOKEN_LAYER_ARM' and result['arm']==spec['arm']==arm
        assert result['tokens']==spec['tokens']==tokens and spec['layer']==5
        assert spec['gets']==0 and spec['thermal'] is False and spec['opp']==1.0
        assert spec['flit_bytes']==32 and spec['max_packet_flits']==16
        assert spec['partitions']==[list(range(4)),list(range(4,8))]
        assert len(run.joinpath('L5_OUTPUT.bin').read_bytes())==tokens*4096
        assert spec['input_sha256']==result['input_sha256']==sha(run/'L5_INPUT.bin')
        assert result['output_sha256']==sha(run/'L5_OUTPUT.bin')
        assert spec['backend_sha256']==read(run/'backend/LAUNCH.json')['binary_sha256']
        assert not (run/'backend/GETS.csv').exists()
        runtime = {key:value for key,value in spec.items() if key!='arm'}
        protocol.append(runtime)
        routing = read(run/'ROUTES.json')
        assert len(routing)==tokens
        routes.append(same_metadata(routing,('token','owner','selected','weights','expert_ranks')))
        matrices = read(run/'MATRICES.json')
        assert matrices and all(1<=m['MKN'][0]<=16 and m['complete']>m['start'] for m in matrices)
        assert all(f'model.layers.5.' in m['label'] or not m['label'].startswith('model.layers.') for m in matrices)
        compute.append(same_metadata(matrices,('label','partition','MKN','source_sha256','output_sha256')))
        payloads.append(same_metadata(messages,('stage','key','src','dst','bytes','payload_sha256')))
        endpoints = sorted({message[key] for message in messages for key in ('src','dst')})
        assert endpoints==result['active_endpoints']==list(range(8))
        pairs = Counter((m['src'],m['dst']) for m in messages)
        assert len(pairs)==result['endpoint_pairs']
        assert len(messages)==result['messages']
        byte_count = sum(m['bytes'] for m in messages)
        cross = sum(m['bytes'] for m in messages if m['src']//4!=m['dst']//4)
        assert 0<cross<byte_count and cross==result['cross_partition_bytes']
        assert all(m['ready_ns']<=m['release_ns']<=m['inject_ns']<m['wire_done_ns']<=m['commit_ns'] for m in messages)
        dispatch = [m for m in messages if m['stage']=='dispatch']
        assert dispatch and all(m['ready_ns']>=routing[m['key'][0]]['ready_ns'] for m in dispatch)
        delivered = {(m['key'][0],m['key'][1]):m['commit_ns'] for m in dispatch}
        assert all(m['ready_ns']>=delivered[m['key'][0],m['key'][1]]
                   for m in messages if m['stage']=='combine')
        active,peak=0,0
        for _,change in sorted([(m['inject_ns'],1) for m in messages]+[(m['wire_done_ns'],-1) for m in messages]):
            active+=change
            peak=max(peak,active)
        assert active==0 and peak==result['peak_in_flight'] and peak>=2
        assert all(m['inject_ns']>=m['release_ns']+40 for m in messages if m['circuit'])
        assert sum(bool(m['circuit']) for m in messages)==result['circuit_messages']
        if arm=='hiband_reference':
            assert result['circuit_messages']==0
            assert any(0<w['local_budget']<1536 and 0<w['global_budget']<1536 for w in traces['waves'])
        else:
            assert all(w['policy_decision'] is not None for w in traces['waves'])
        receipt[arm] = dict(result,bytes=byte_count,cross_fraction=cross/byte_count,matrices=len(matrices))
    assert protocol[0]==protocol[1] and routes[0]==routes[1] and payloads[0]==payloads[1]
    assert compute[0]==compute[1] and receipt[ARMS[0]]['output_sha256']==receipt[ARMS[1]]['output_sha256']
    return dict(tag=tag,tokens=tokens,arms=receipt,placement=protocol[0],
                project_minus_hiband_ns={k:receipt[ARMS[1]][k]-receipt[ARMS[0]][k] for k in METRICS})


if __name__=='__main__':
    root=Path(sys.argv[1]).resolve()
    tokens=int(sys.argv[2])
    tags=sys.argv[3:]
    cases=[audit(root,tag,tokens) for tag in tags]
    assert len({c['placement']['input_sha256'] for c in cases})==len(cases)
    result=dict(status='PASS_MULTITOKEN_PAIR',tokens=tokens,cases=cases,
                scope='Real layer-5 FP16/K64 operators and Ramulator endpoint callbacks; fixed phase-ready '
                      'sets with concurrent PopNet packets. CS uses the modeled circuit lane with the existing '
                      'wiring. Input tensors are frozen diagnostic layer entries.')
    path=root/f'SUMMARY_{tokens}.json'
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(result,indent=2)+'\n')
    temp.replace(path)
    print(json.dumps(result))
