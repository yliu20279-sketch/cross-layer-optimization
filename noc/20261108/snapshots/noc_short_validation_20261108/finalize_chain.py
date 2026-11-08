"""Finalize completed short-chain evidence; never rerun/edit native inputs."""
from pathlib import Path
import datetime,hashlib,json
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
audit=json.loads((R/'chain_acceptance_retry1.json').read_text())
assert set(audit['cases'])=={'absolute','relative'}
assert all(v['state']=='passed' for v in audit['cases'].values())
paths={}
proofs={}
for mode in ('absolute','relative'):
    case=R/mode;rid=json.loads((case/'result.json').read_text())['rounds']
    paths[mode]=case/'run'/f'proc_r{rid}_p2_t0'
    for filename in ('independent_NoC_validation.json','independent_native_DRAM.json',f'oracle_round{rid-1}.json',f'oracle_round{rid}.json'):
        p=case/'evidence_retry1'/filename
        assert json.loads(p.read_text())['state']=='passed'
        proofs[str(p)]=sha(p)
names=['source.csv','events.csv','receive_events.csv','receive_ready_events.csv','wire_headers.csv',
       'bridge_summary.json','receive_summary.json','receive_ready_summary.json','router_stalls.csv',
       'router_stalls_packets.csv','router_stalls_forwarded.csv','router_stalls_forward_busy.csv',
       'router_stalls_packet_forwarded.csv','output_delayInfo.txt','control_events.csv','phase_demand.json']
checks={name:sha(paths['absolute']/name)==sha(paths['relative']/name) for name in names}
assert all(checks.values()),checks
inputs=json.loads((R/'chain_input_hashes.json').read_text())
assert all(sha(Path(p))==h for p,h in inputs.items())
result={'state':'passed','time':datetime.datetime.now().isoformat(),'cases':audit['cases'],
        'scope':'short real native vector/DMA/DRAM program with actual NI configuration and receive-ready packets',
        'not_complete_Qwen_or_performance_result':True,'target_NPUs':16,'real_Ramulator2_partitions':16,
        'DRAM_capacity_bytes':34359738368,'predictor_modes_same_physical_result':True,
        'cross_predictor_exact_checks':checks,'original_simulation_inputs_unchanged':len(inputs),
        'independent_reference_proof_hashes':proofs,
        'auditor_sha256':sha(R/'audit_chain_retry1.py'),'finalizer_sha256':sha(Path(__file__)),
        'historical_failed_audits_preserved':True,
        'first_audit_issue':'incorrectly equated sender and receiver request times; independent READ posts are now checked',
        'retry1_finalization_issue':'cross-mode comparator expected a differently named feedback file; native data unchanged'}
(R/'accepted_chain_validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
