"""Exhaustive local CS connectivity regression on the accepted NoC binary.

Artificial protocol fixtures, not application/performance measurements.
Each positive case includes real receive-ready packets and competing Mesh data.
"""
from pathlib import Path
from collections import Counter
from itertools import permutations
import csv, datetime, hashlib, json, os, subprocess

R = Path(__file__).resolve().parent
TARGET = Path('/mnt/sda1/h4567/qwen15_moe_target_v36_20261009')
OUT = R/'runs'
OUT.mkdir(exist_ok=False)
state = {'state': 'running', 'scope': 'exhaustive CS connectivity/protocol fixtures; not application performance',
         'cases': [], 'ready_protocol': True, 'CS_count': 9}

def save():
    state['updated'] = datetime.datetime.now().isoformat()
    temp = R/'status.tmp'
    temp.write_text(json.dumps(state, indent=2))
    temp.replace(R/'status.json')

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def corners(c):
    row, col = divmod(c, 3)
    return [(row+dy)*4+col+dx for dy, dx in ((0,0),(0,1),(1,0),(1,1))]

def encode(pairs):
    # Ordered physical port names NW, NE, SW, SE; omit the output's own input.
    value = 0
    for i, o in pairs:
        assert i != o
        value |= (4+[p for p in range(4) if p != o].index(i)) << (3*o)
    return value

def run(name, c, pairs, invalid=None):
    case = OUT/name
    case.mkdir()
    nodes = corners(c)
    tx = {nodes[i] for i,o in pairs}
    rx = {nodes[o] for i,o in pairs}
    cs_state = encode(pairs)
    if invalid == 'input_reuse':
        cs_state = encode([(0,1),(0,2)])
        tx, rx = {nodes[0]}, {nodes[1],nodes[2]}
    elif invalid == 'selector_3':
        cs_state = 7
    elif invalid == 'disabled_nonzero':
        cs_state = 1
    cfg = 'params 2 1 1 3 1\n'
    cfg += ''.join('cs %d %d\n' % (j, cs_state if j==c else 0) for j in range(9))
    cfg += ''.join('node %d %d %d\n' % (n, 16+c if n in tx else 0, 16+c if n in rx else 0) for n in range(16))
    routes, messages, expected_aux = [], [], set()
    if invalid is None:
        for i,o in pairs:
            s,d = nodes[i],nodes[o]
            routes.append('route %d %d %d %d\n' % (len(messages),s,d,s))
            expected_aux.add((s,d))
            messages.append((s,d,2048))
        outside = next(n for n in range(16) if n not in nodes)
        # Deliver ordinary Mesh data to each same receiver as the CS traffic.
        messages.extend((outside,nodes[o],2048) for i,o in pairs)
    (case/'config.txt').write_text(cfg+''.join(routes))
    calendar, bench, counts = [], [], Counter()
    for p,(s,d,size) in enumerate(messages):
        ident = 0x4e4f800000000000 | ((p+1)<<24) | (s<<8) | d
        bench.append('1 1 %d %d 65 %d\n' % (s,d,ident))
        calendar.extend(['post %d %d %d 1 %d %d\n' % (d,s,ident,size,1048576+32768*counts[d]),
                         'descriptor %d %d %d\n' % (d,ident,3900000+32*counts[d])])
        counts[d] += 1
    # Fixed shared-port occupancy from an independent synthetic NPU schedule.
    busy = {(n,t) for n in rx for t in range(100,12000,31)} if invalid is None else set()
    calendar.extend('use %d %d 256\n' % p for p in sorted(busy))
    (case/'bench.txt').write_text(''.join(bench))
    (case/'calendar.txt').write_text(''.join(calendar))
    env = {k:v for k,v in os.environ.items() if not k.startswith('NOC_')}
    env.update(NOC_DATA_WIRE='1', NOC_AUX_CONFIG=str(case/'config.txt'), NOC_AUX_LOG='events.csv',
               NOC_SOURCE_CAPACITY_FLITS='1025', NOC_SOURCE_LOG='source.csv',
               NOC_RECEIVE_POSTS=str(case/'calendar.txt'), NOC_SRAM_POLICY='npu_first',
               NOC_RECEIVE_READY='1', NOC_STABLE_EVENT_ORDER='2', NOC_CLOCKED_SOURCE_ADMISSION='1',
               NOC_QUIESCENT_SKIP='0', NOC_EMPTY_SKIP='1', NOC_IDLE_ROUTER_FAST='1')
    args = [str(R/'popnet_cs_ni'),'-A','16','-c','1','-V','3','-B','8','-O','8','-F','4',
            '-R','4','-L','2000','-G',str(TARGET/'noc_mesh_4x4_v3_6_candidate.gv'),
            '-T','30000','-r','1','-I',str(case/'bench.txt'),'-D','delay.txt','-P']
    with (case/'run.log').open('xb') as f:
        cp = subprocess.run(args,cwd=case,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=90)
    if invalid:
        reason = {'input_reuse':'CS input reused','selector_3':'illegal CS SEL/EN',
                  'disabled_nonzero':'illegal CS SEL/EN'}[invalid]
        assert cp.returncode != 0 and reason in (case/'run.log').read_text(), (name,cp.returncode)
        result = {'name':name,'state':'invalid_physical_configuration_rejected','reason':reason}
    else:
        assert cp.returncode == 0, (name,cp.returncode,(case/'run.log').read_text()[-1200:])
        bridge = json.loads((case/'bridge_summary.json').read_text())
        ready = json.loads((case/'receive_ready_summary.json').read_text())
        wire = json.loads((case/'wire_summary.json').read_text())
        count, aux = len(messages), len(pairs)*65
        assert bridge['completed_packets']==count and bridge['control_retired_flits']==count
        assert bridge['aux_written']==bridge['aux_sent']==bridge['aux_credits_returned']==aux
        assert bridge['mesh_written']==aux and bridge['written_flits']==count*65
        assert bridge['max_aux_fifo']<=2
        assert ready['state']=='passed' and ready['notifications']==ready['received']==ready['data_admissions']==count
        assert wire['serialized_control_headers']==count and not wire['router_uses_packet_table']
        assert wire['serialized_data_headers']==count and wire['unchanged_body_flits']==count*64
        with (case/'wire_headers.csv').open() as f:
            headers=list(csv.DictReader(f))
        source={(v['packet'],v['source'],v['destination']):v['wire_word'] for v in headers if v['event'] in ('SOURCE','SOURCE_CONTROL')}
        aux_rx=Counter()
        for v in headers:
            assert v['wire_word']==source[v['packet'],v['source'],v['destination']]
            if v['event']=='AUX_RX_HEADER':
                s,d=int(v['source']),int(v['destination'])
                assert int(v['node'])==d and (s,d) in expected_aux
                aux_rx[s,d]+=1
        assert aux_rx==Counter({pair:1 for pair in expected_aux})
        service=Counter()
        with (case/'source.csv').open() as f:
            for v in csv.DictReader(f):
                if v['event']=='RELEASE':service[int(v['node']),int(float(v['time']))]+=1
        with (case/'receive_events.csv').open() as f:
            for v in csv.DictReader(f):
                if int(v['bytes']):service[int(v['node']),int(float(v['time']))]+=1
        assert service and max(service.values())==1 and not set(service)&busy
        result={'name':name,'state':'passed','CS':c,'directed_connections':pairs,
                'data_packets':count,'real_ready_controls':count,'aux_flits':aux,
                'mesh_flits':aux,'single_shared_SRAM_port_checked':True,
                'serialized_header_preserved_and_physical_receiver_checked':True}
    (case/'validation.json').write_text(json.dumps(result,indent=2))
    state['cases'].append(result)
    save()

save()
try:
    state['binary_sha256']=sha(R/'popnet_cs_ni')
    assert state['binary_sha256']=='e6058e940931db3835c4bef6704354aac10851070bc1e0c1f90b65a3f033278a'
    for c in range(9):
        for i in range(4):
            for o in range(4):
                if i != o:run('cs%d_%d_to_%d'%(c,i,o),c,[(i,o)])
        ds=[p for p in permutations(range(4)) if all(i!=o for o,i in enumerate(p))]
        assert len(ds)==9
        for k,p in enumerate(ds):run('cs%d_permutation%d'%(c,k),c,[(i,o) for o,i in enumerate(p)])
        for bad in ('input_reuse','selector_3','disabled_nonzero'):
            run('cs%d_invalid_%s'%(c,bad),c,[],invalid=bad)
    assert len(state['cases'])==216
    state.update(state='passed',single_directed_cases=108,full_unicast_permutation_cases=81,
                 rejected_invalid_cases=27,application_performance_claim=False)
except BaseException as e:
    state.update(state='failed',reason=repr(e))
    save()
    raise
finally:save()
