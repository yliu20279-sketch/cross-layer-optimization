"""Audit completed OPP and mixed native diagnostic receipts against the reference."""

from collections import Counter
import json
import math
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def main(runs, refs, output, prefix='joint_fixed_'):
    locked = read(refs/'NATIVE_TIMED_SERVICES.json')
    frozen = [e for seg in locked['segments'] for e in seg['events'] if e['kind']=='native_matrix_rpc']
    fixed = {q:read(runs/f'opp{q}'/'RESULT.json') for q in (2,3,4)}
    for q, run in fixed.items():
        assert run['status']=='PASS_NATIVE_OPP_CALIBRATION' and run['opp_quarters']==q and run['matrices']==len(frozen)
        assert run['output_sha256']==fixed[4]['output_sha256']
    for k, item in enumerate(frozen):
        base = fixed[4]['timing'][k]
        assert (base['actual_start'],base['complete'])==(item['start'],item['done'])
        assert base['compute_cycles']==item['native_lowering']['compute_cycles']
        for q in (2,3):
            lowered=fixed[q]['timing'][k]
            assert abs(lowered['compute_cycles']-base['compute_cycles']*4/q)<1
            assert lowered['complete']-lowered['actual_start'] > base['complete']-base['actual_start']
            assert lowered['dram_requests']==base['dram_requests']
    calibration = [dict(opp=q/4,full_layer_ns=data['target_complete'],
                        matrix_ns=sum(r['complete']-r['actual_start'] for r in data['timing']),
                        compute_ns=sum(r['compute_cycles'] for r in data['timing']),
                        sram_bank_ns=sum(r['sram_bank_cycles'] for r in data['timing']))
                   for q,data in sorted(fixed.items(),reverse=True)]
    cases=[]
    for name in ('combined_overload','matched'):
        out=runs/f'{prefix}{name}'
        run=read(out/'RESULT.json')
        baseline=read(refs/name/'RECEIPT.json')
        policy=read(out/'NETWORK_POLICY.json')
        assert run['status']=='PASS_NATIVE_MOE_GETS_THERMAL_DIAGNOSTIC' and run['case']==name
        assert run['gets']==baseline['gets_transactions'] and run['output_sha256']==fixed[4]['output_sha256']
        assert policy['gets_sha256']==read(refs/name/'LAUNCH.json')['arrivals_sha256']
        assert run['joined_makespan']==max(run['moe_suffix'],run['gets_last_reply'])
        assert len(run['thermal']['decisions'])==len(run['timing'])==25
        origin=run['backend_summary']['clock_ns']-run['joined_makespan']
        duration_errors=[]
        for index, (decision, actual) in enumerate(zip(run['thermal']['decisions'],run['timing'])):
            assert decision['task_id']==index and decision['cluster']==actual['rank']
            assert round(4*decision['chosen_opp'])==actual['opp_quarters']
            assert math.ceil(decision['scheduled_start_ns'])+origin==actual['actual_start']
            assert actual['rpc_ready']<=actual['actual_start']<actual['complete']
            profile=fixed[actual['opp_quarters']]['timing'][index]
            duration_errors.append(abs((actual['complete']-actual['actual_start'])-
                                       (profile['complete']-profile['actual_start'])))
        cases.append(dict(case=name, gets=run['gets'], network_policy=policy['selected'],
                          hiband_last_reply=baseline['last_response'], joint_last_reply=run['gets_last_reply'],
                          hiband_moe_suffix=baseline['moe_done'], joint_moe_suffix=run['moe_suffix'],
                          hiband_join=baseline['mixed_join'], joint_join=run['joined_makespan'],
                          selected_opp_counts=dict(Counter(r['opp_quarters']/4 for r in run['timing'])),
                          delayed_starts=sum(r['actual_start']>r['rpc_ready'] for r in run['timing']),
                          deferred_ns=sum(r['actual_start']-r['rpc_ready'] for r in run['timing']),
                          max_profile_duration_error_ns=max(duration_errors)))
    receipt=dict(status='PASS_PAIRED_DIAGNOSTIC_NOT_FORMAL_PERFORMANCE', calibration=calibration,
                 matrix_count=len(frozen), cases=cases,
                 limitations=['Thermal uses the published RC/activity coefficients, with current native timings.',
                              'HiBand reference and native backend have different network and endpoint implementations.'])
    output.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':
    main(*(Path(s) for s in sys.argv[1:4]),*sys.argv[4:])
