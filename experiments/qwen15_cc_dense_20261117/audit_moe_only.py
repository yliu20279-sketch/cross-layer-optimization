"""Verify the no-GetS comparison and report the MoE critical-path timings."""

import json
from pathlib import Path
import sys

from audit_noc_only import digest, read


def main(root, out):
    manifest = {
        Path(path).name: sha
        for sha, path in (line.split(maxsplit=1) for line in (out/'INPUTS.sha256').read_text().splitlines())
    }
    contract_path = root/'combined_overload/CONTRACT.json'
    contract = read(contract_path)
    assert manifest['CONTRACT.json'] == digest(contract_path)
    assert manifest['NATIVE_TIMED_SERVICES.json'] == digest(root/'NATIVE_TIMED_SERVICES.json')
    assert manifest['run.py'] == digest(out/'run.py')
    screening = read(out/'rtl_screen/RESULT.json')
    assert screening['contract_sha256'] == manifest['CONTRACT.json']
    assert screening['gets']==0 and screening['selected']=='mesh'
    assert screening['rtl_sha256'] == manifest['Vunified_tb']
    assert sum(pair['messages'] for pair in screening['pairs']) == len(contract['transport']) == 15
    gains = [trial['gain_cycles'] for pair in screening['pairs'] for trial in pair['trials']]
    assert len(screening['pairs'])==6 and gains and all(gain<=1 for gain in gains)
    arms = {}
    launch_keys = []
    tracks = []
    metrics = ('moe_transport_ns','moe_suffix_ns','target_complete')
    for arm, mode in (('hiband_reference','FULL_LOCAL'),('project_noc','mesh')):
        directory = out/arm
        result = read(directory/'RESULT.json')
        inputs = read(directory/'INPUTS.json')
        policy = read(directory/'NETWORK_POLICY.json')
        launch = read(directory/'backend/LAUNCH.json')
        for record in (inputs,policy,result):
            assert record['thermal_enabled'] is False
        assert result['status']=='PASS_NATIVE_MOE_ONLY_PAIR_ARM'
        assert result['gets']==policy['gets']==0 and not (directory/'backend/GETS.csv').exists()
        assert policy['paired_policy']==arm and policy['selected']==result['selection']==mode
        assert result['frozen_contract_sha256']==manifest['CONTRACT.json']
        assert inputs['frozen_sha256']==manifest['NATIVE_TIMED_SERVICES.json']
        assert inputs['binary_sha256']==launch['binary_sha256']==manifest['coupled_backend']
        assert inputs['input_sha256']==contract['source_sha256']['prefill_L5_input.bin']
        assert result['output_sha256']==contract['source_sha256']['prefill_L5_output.bin']
        assert len(result['timing'])==result['matrices']==25
        assert all(r['opp_quarters']==4 and r['actual_start']==r['rpc_ready']<r['complete'] for r in result['timing'])
        command = launch['command']
        assert Path(command[-2]).name=='ramulator32.yaml' and command[-1]=='off'
        launch_keys.append((command[:-3],command[-2:],
                            {k:v for k,v in launch['environment'].items() if k!='POPNET_STATS_DIR'}))
        transport = read(directory/'TRANSPORT.json')
        start = next(i for i,event in enumerate(transport) if event['stage']=='dispatch')
        moe = transport[start:]
        assert len(moe)==result['moe_messages']==15
        keys = ('stage','src','dst','bytes','payload_sha256')
        assert all(all(event[k]==expected[k] for k in keys) for event,expected in zip(moe,contract['transport']))
        assert all(a['complete']<=b['start'] for a,b in zip(transport,transport[1:]))
        assert result['moe_origin_ns']==moe[0]['start']
        assert result['moe_suffix_ns']==result['target_complete']-moe[0]['start']
        assert result['moe_transport_ns']==sum(e['complete']-e['start'] for e in moe)
        backend = result['backend_summary']
        runtime = result['paired_policy']
        assert backend['packets']==backend['packet_callbacks']==runtime['admitted_packets']
        assert backend['transactions']==backend['callbacks'] and backend['link_switches']==0
        assert runtime['global_bytes']==0 and runtime['local_budget']==1536
        tracks.append((result['timing'],transport))
        arms[arm] = {key:result[key] for key in metrics}
        arms[arm].update(selected=mode,origin_ns=result['moe_origin_ns'],moe_messages=len(moe),
                         full_layer_packets=backend['packets'],result_sha256=result['output_sha256'])
    assert launch_keys[0]==launch_keys[1]
    receipt = dict(status='PASS_NATIVE_MOE_ONLY_PAIR', host='113',
                   remote_dir=(root/'moe_only_remote_path.txt').read_text().strip(), gets=0,
                   thermal_enabled=False, opp=1.0, matrices=25, serialized=True,
                   sources=manifest, rtl_pairs=len(screening['pairs']), rtl_candidates=len(gains),
                   rtl_candidate_gain_cycles_range=[min(gains),max(gains)], arms=arms,
                   difference_project_minus_hiband_ns={
                       key:arms['project_noc'][key]-arms['hiband_reference'][key] for key in metrics},
                   matrix_trace_equal=tracks[0][0]==tracks[1][0],
                   transport_trace_equal=tracks[0][1]==tracks[1][1],
                   timing=dict(moe_transport_ns='Sum of native send-to-destination-commit intervals for 15 MoE messages',
                               moe_suffix_ns='First MoE dispatch release to layer result',target_complete='Layer entry to layer result'),
                   scope='Common native PopNet Mesh and endpoint services. Project selection uses the reactive '
                         'single-transfer RTL screen; HiBand is the local bandwidth reference.')
    (out/'SUMMARY.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__=='__main__':
    main(*(Path(arg).resolve() for arg in sys.argv[1:]))
