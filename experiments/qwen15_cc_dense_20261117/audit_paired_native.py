"""Audit the two-strategy native PopNet/Ramulator2 comparison."""

import json
from pathlib import Path
import sys

from audit_noc_only import digest, read, transaction_rows


CASES = {'combined_overload': 256, 'matched': 512}
ARMS = {'hiband_reference': 'FULL_LOCAL', 'project_noc': 'mesh'}
METRICS = ('gets_last_reply_ns', 'gets_max_latency_ns', 'moe_suffix_ns', 'join_ns')


def main(root, runs):
    manifest = {
        Path(path).name: sha
        for sha, path in (line.split(maxsplit=1) for line in (runs/'INPUTS.sha256').read_text().splitlines())
    }
    freeze_path = root/'NATIVE_TIMED_SERVICES.json'
    audit_path = root/'noc_only_results/RTL_INGRESS.json'
    assert manifest['NATIVE_TIMED_SERVICES.json'] == digest(freeze_path)
    paired_runner = runs/'run_pair.py'
    assert manifest['run_pair.py'] == digest(paired_runner if paired_runner.exists() else root/'run_native_opp.py')
    assert manifest['RTL_INGRESS.json'] == digest(audit_path)
    rtl = {row['case']:row['selected'] for row in read(audit_path)['cases']}
    calibration = read(root/'native_opp_results/opp4/RESULT.json')
    reference_launch = None
    cases = []
    for case, count in CASES.items():
        source = root/f'{case}.json'
        source_sha = digest(source)
        assert source_sha == manifest[source.name]
        arrivals = read(source)['transactions']
        contract = read(root/case/'CONTRACT.json')
        assert len(arrivals) == count
        assert all(t['request_bytes']==32 and t['reply_bytes']==64 and (t['src'],t['dst'])==(0,1)
                   for t in arrivals)
        assert all(t['src'] in range(4) and t['dst'] in range(4) for t in contract['transport'])
        assert rtl[case] == ARMS['project_noc']
        runs_for_case = {}
        for arm, chosen in ARMS.items():
            arm_dir = runs/f'{case}-{arm}'
            backend = arm_dir/'backend'
            result = read(arm_dir/'RESULT.json')
            config = read(arm_dir/'NETWORK_POLICY.json')
            inputs = read(arm_dir/'INPUTS.json')
            launch = read(backend/'LAUNCH.json')
            execution = read(backend/'PAIRED_POLICY.json')
            events = read(arm_dir/'TRANSPORT.json')
            gets = transaction_rows(backend/'GETS.csv')
            matrix = transaction_rows(backend/'OPP_MATRIX.csv')
            assert result['status'] == 'PASS_NATIVE_PAIRED_NOC_DIAGNOSTIC'
            assert result['case'] == case
            assert not any(record['thermal_enabled'] for record in (result,config,inputs))
            assert inputs['opp_quarters'] == result['opp_quarters'] == 4
            assert inputs['input_sha256'] == contract['source_sha256']['prefill_L5_input.bin']
            assert result['output_sha256'] == calibration['output_sha256']
            assert inputs['frozen_sha256'] == manifest['NATIVE_TIMED_SERVICES.json']
            assert config['gets_sha256'] == source_sha and config['audit_sha256'] == manifest['RTL_INGRESS.json']
            assert inputs['binary_sha256'] == launch['binary_sha256'] == manifest['coupled_backend']
            assert config['selected'] == chosen and config['paired_policy'] == arm
            command = launch['command']
            assert command[-1] == 'off' and Path(command[-2]).name == 'ramulator32.yaml'
            launch_key = (command[:-3], command[-2:],
                          {k:v for k,v in launch['environment'].items() if k != 'POPNET_STATS_DIR'})
            if reference_launch is None:
                reference_launch = launch_key
            assert reference_launch == launch_key
            assert result['paired_policy'] == execution and execution['policy'] == arm
            assert execution['mode'] == ('FULL_LOCAL' if arm == 'hiband_reference' else 'SHARED')
            assert execution['local_budget'] == execution['total_budget_bytes_per_tick'] == 1536
            assert execution['global_budget'] == (0 if arm == 'hiband_reference' else 1536)
            assert execution['global_bytes'] == 0
            assert len(matrix) == len(result['timing']) == result['matrices'] == 25
            for raw, observed, fixed in zip(matrix,result['timing'],calibration['timing']):
                assert all(observed[k] == v for k,v in raw.items())
                assert observed['opp_quarters'] == 4
                assert observed['rpc_ready'] == observed['actual_start'] < observed['complete']
                assert all(observed[k] == fixed[k] for k in ('rank','compute_cycles','sram_bank_cycles','dram_requests'))
            assert len(gets) == len(arrivals) == count == result['gets']
            for actual, expected in zip(gets,arrivals):
                assert (actual['id'],actual['arrival']) == (expected['id'],expected['arrival'])
                a,b,c,d,e,f = (actual[k] for k in
                               ('arrival','request_inject','request_done','read_done','reply_inject','reply_done'))
                assert a <= b < c < d <= e < f
            tail = max(r['reply_done'] for r in gets)
            slowest = max(gets,key=lambda r:r['reply_done']-r['arrival'])
            assert tail == result['gets_last_reply']
            stats = result['backend_summary']
            assert stats['transactions'] == stats['callbacks']
            assert stats['packets'] == stats['packet_callbacks'] == execution['admitted_packets']
            assert stats['link_switches'] == stats['mapping_installs'] == stats['migration_write_bytes'] == 0
            assert result['joined_makespan'] == stats['clock_ns']-result['mixed_origin_ns']
            assert result['moe_suffix'] == result['target_complete']-result['mixed_origin_ns']
            assert result['joined_makespan'] == max(result['moe_suffix'],tail)
            runs_for_case[arm] = dict(
                selected=chosen, gets_last_reply_ns=tail,
                gets_max_latency_ns=slowest['reply_done']-slowest['arrival'],
                slowest_gets_id=slowest['id'],
                slowest_gets_service_ns=slowest['read_done']-slowest['request_done'],
                moe_suffix_ns=result['moe_suffix'], join_ns=result['joined_makespan'],
                full_layer_ns=result['target_complete'], origin_ns=result['mixed_origin_ns'],
                admitted_packets=stats['packets'], local_admitted_bytes=execution['local_bytes'],
                budget_wait_events=execution['budget_wait_events'],
                gets_trace_sha256=digest(backend/'GETS.csv'),
                matrix_trace_sha256=digest(backend/'OPP_MATRIX.csv'), transport_trace_sha256=digest(arm_dir/'TRANSPORT.json'),
                transport_events=len(events))
        hb, noc = (runs_for_case[arm] for arm in ARMS)
        cases.append(dict(
            case=case, gets=count, frozen_arrivals_sha256=source_sha, arms=runs_for_case,
            project_minus_hiband_ns={m:noc[m]-hb[m] for m in METRICS},
            gets_trace_equal=hb['gets_trace_sha256']==noc['gets_trace_sha256'],
            matrix_trace_equal=hb['matrix_trace_sha256']==noc['matrix_trace_sha256'],
            transport_trace_equal=hb['transport_trace_sha256']==noc['transport_trace_sha256']))
    receipt = dict(
        status='PASS_NATIVE_PAIRED_REFERENCE_DIAGNOSTIC', host='113',
        remote_dir=(root/'paired_native_remote_path.txt').read_text().strip(),
        layer='Qwen1.5-MoE-A2.7B-Chat-GPTQ-Int4 layer 5 prefill one token', thermal_enabled=False,
        opp=1.0, gets_drams_per_request=2, gets_dram_bytes_per_read=32,
        gets_completion_gate='Two read acknowledgements before reply, enforced in the common native backend',
        time_origin='First offered GetS arrival; join = max(MoE layer result, last GetS reply)',
        sources=manifest, output_sha256=calibration['output_sha256'], cases=cases,
        scope='Native single-layer diagnostic. Both use PopNet Mesh; the HiBand arm is the project four-mode '
              'bandwidth reference, not physical split-Benes. Only local traffic and FULL_LOCAL were covered. '
              'The project arm used the retained Mesh decision from the first-dispatch RTL audit.')
    (runs/'SUMMARY.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main(*(Path(arg).resolve() for arg in sys.argv[1:]))
