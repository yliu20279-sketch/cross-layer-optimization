"""Audit native NoC-only mixed runs against the frozen layer and GetS inputs."""

import csv
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transaction_rows(path):
    with path.open(newline='') as stream:
        return [{k:int(v) for k,v in row.items()} for row in csv.DictReader(stream)]


def main(root, out):
    trials = out/'RTL_INGRESS.json'
    chosen = {row['case']:row['selected'] for row in read(trials)['cases']}
    full_frequency = read(root/'native_opp_results/opp4/RESULT.json')
    cases = []
    for case, count in (('combined_overload',256),('matched',512)):
        directory = out / case
        result = read(directory/'RESULT.json')
        policy = read(directory/'NETWORK_POLICY.json')
        inputs = read(directory/'INPUTS.json')
        source = root/f'{case}.json'
        arrivals = read(source)['transactions']
        gets = transaction_rows(directory/'GETS.csv')
        assert len(gets) == len(arrivals) == count == result['gets']
        assert result['status']=='PASS_NATIVE_NOC_MOE_GETS_DIAGNOSTIC' and result['case']==case
        assert not any(record['thermal_enabled'] for record in (result, policy, inputs))
        assert policy['selected']==chosen[case] and policy['audit_sha256']==digest(trials)
        assert policy['gets_sha256']==digest(source)
        assert result['output_sha256']==full_frequency['output_sha256']
        assert len(result['timing'])==25
        for actual, base in zip(result['timing'],full_frequency['timing']):
            assert actual['opp_quarters']==4 and actual['rpc_ready']==actual['actual_start']<actual['complete']
            assert tuple(actual[k] for k in ('rank','compute_cycles','sram_bank_cycles','dram_requests'))==tuple(
                base[k] for k in ('rank','compute_cycles','sram_bank_cycles','dram_requests'))
        for actual, expected in zip(gets, arrivals):
            assert actual['id']==expected['id'] and actual['arrival']==expected['arrival']
            points = [actual[k] for k in ('arrival','request_inject','request_done','read_done','reply_inject','reply_done')]
            assert points==sorted(points) and points[0]==points[1]<points[2]<points[3]
        tail=max(gets,key=lambda row:row['reply_done'])
        assert tail['reply_done']==result['gets_last_reply']
        assert result['joined_makespan']==max(result['moe_suffix'],tail['reply_done'])
        stats = result['backend_summary']
        assert stats['transactions']==stats['callbacks'] and stats['packets']==stats['packet_callbacks']
        previous_dir=root/'native_opp_results'/f'joint_ready_{case}'
        previous=read(previous_dir/'RESULT.json')
        cases.append(dict(case=case,gets=count,network=policy['selected'],thermal=False,opp=1.0,
                          gets_last_reply_ns=tail['reply_done'],gets_max_latency_ns=max(r['reply_done']-r['arrival'] for r in gets),
                          moe_suffix_ns=result['moe_suffix'],join_ns=result['joined_makespan'],
                          full_layer_ns=result['target_complete'],matrices=len(result['timing']),
                          prior_thermal_join_ns=previous['joined_makespan'],
                          gets_trace_equal_to_prior_thermal=digest(directory/'GETS.csv')==digest(previous_dir/'GETS.csv')))
    summary=dict(status='PASS_NATIVE_NOC_ONLY_TWO_CASES',cases=cases,
                 source='first-dispatch RTL policy selection and full native one-layer execution')
    (out/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    main(*(Path(arg).resolve() for arg in sys.argv[1:]))
