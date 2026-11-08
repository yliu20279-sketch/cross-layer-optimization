"""One real decoder-block pilot with no fabricated or scaled delays."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import time
from supervise import supervised_run

ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
TARGET=Path('/mnt/sda1/h4567/qwen15_moe_target_v36_20261009')
SIM=BASE/'LEGOSIM_NPU_R2_V20260831'
ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--seed',type=Path,required=True)
ap.add_argument('--observer-only',action='store_true');ap.add_argument('--predictor',choices=['absolute','relative'],default='absolute')
ap.add_argument('--rounds',type=int,default=1);ap.add_argument('--timeout',type=int,default=14400)
ap.add_argument('--plan',type=Path,required=True)
ap.add_argument('--mode',choices=['mesh','static_cs'],default='mesh')
args=ap.parse_args()
assert 1<=args.rounds<=128 and 60<=args.timeout<=172800
case=ROOT/args.name;case.mkdir(exist_ok=False);work=case/'run';work.mkdir()
status={'state':'preparing','application_performance_claim':False,'complete_NoC_experiments':False,
        'clock_edge_order':'credit/wire arrivals before router; one clocked source-admission phase',
        'physical_resource_budget_unchanged':True,'legacy_undefined_same_cycle_order_is_not_reference':True,
        'scope':'real Qwen1.5-MoE decoder blocks; selected validated plan; target architecture',
        'NPU':16,'Ramulator2':16,'DRAM_bytes':34359738368,'mapping':'TP16+EP16/PP1',
        'numerical_predictor':args.predictor+'_with_actual_native_program_waits','maximum_rounds':args.rounds,
        'DRAM_clock_includes_idle':True,'SRAM_policy':'NPU > data source NI > protocol/receive NI'}
status['HB_service']={'bytes':128,'cycles':5,'fixed_electrical_latency_ns':None,
                      'scope':'serialization occupancy; unknown electrical latency not filled in'}
status['NoC_case_mode']=args.mode
def save(): (case/'status.json').write_text(json.dumps(status,indent=2))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
save();started=time.monotonic()
try:
    assert json.loads((ROOT/'runtime_preparation_status.json').read_text())['state']=='passed'
    prep=json.loads((ROOT/'runtime_preparation_status.json').read_text())
    for name,digest in prep['binaries'].items():assert sha(ROOT/name)==digest
    plans=args.plan.resolve()
    allocation=json.loads((plans/'layout_audit.json').read_text())
    status['decoder_blocks']=allocation['layer_limit'];save()
    assert allocation['state']=='allocation_and_shard_checks_passed'
    assert json.loads((plans/'independent_layout_check.json').read_text())['state']=='passed'
    assert json.loads((BASE/'qwen15_wallclock_native_20261107/packing_validation.json').read_text())['state']=='passed'
    assert json.loads((ROOT/'capacity_validation.json').read_text())['state']=='capacity_reservations_passed'
    (case/'plan_pointer.json').write_text(json.dumps({'path':str(plans)}))
    clocks_path=BASE/'qwen15_wallclock_native_20261107/clock_domain_mapping.json'
    clocks=json.loads(clocks_path.read_text());assert clocks['global_time_unit_ns']==1
    assert clocks['domains']['npu']['cycle_ns']==clocks['domains']['noc']['cycle_ns']==1
    assert clocks['domains']['dram']['cycle_ns']==clocks['ramulator_wrapper_cycle_scale']==1.25
    backend=BASE/'ramulator_wallclock_20261107';ram=backend/'build/ramulator2'
    backend_proof=json.loads((backend/'validated_server.json').read_text())
    assert backend_proof['state']=='passed' and sha(ram)==backend_proof['binary_sha256']
    assert args.seed.is_file();shutil.copy2(args.seed,work/'delayInfo.txt')
    (case/'seed_provenance.json').write_text(json.dumps({'path':str(args.seed),'sha256':sha(args.seed),
        'purpose':'actual prior feedback is a numerical initial guess only; not this protocol performance'},indent=2))
    profile=work/'noc_port_profile';profile.mkdir();(work/'reports').mkdir()
    for n in range(16):(profile/('node_%d.txt'%n)).write_text('')
    (work/'all_off.cfg').write_text('params 2 1 1 3 1\n'+
        ''.join('cs %d %d\n'%(c,2048 if args.mode=='static_cs' and c==0 else 0) for c in range(9))+
        ''.join('node %d %d %d\n'%(n,16 if args.mode=='static_cs' and n==0 else 0,
                                  16 if args.mode=='static_cs' and n==5 else 0) for n in range(16)))
    topo=BASE/'qwen15_tp_graph_20261107/npusim_one_array_explicit.gv'
    binary=ROOT/'npu/build/endpoint_decoder';core=ROOT/'core/build/interchiplet'
    yml=['phase1:\n']
    for n in range(16):
        assert allocation['nodes'][n]['plan_sha256']==sha(plans/('node_%d.json'%n))
        yml.append(f'- role: dram_proxy\n  id: CH{n}\n  cmd: {ram}\n  args:\n  - "{n%4}"\n  - "{4+n//4}"\n  - "1.25"\n  - --server\n  - {TARGET}/ramulator2_hb_partition_v3_6_candidate.yaml\n  - "2147483648"\n  - "1"\n  - ../reports/ramulator2_ch{n}.csv\n  log: ramulator2.ch{n}.log\n  is_to_stdout: false\n  clock_rate: 1\n')
    for n in range(16):
        yml.append(f'- role: npu\n  id: N{n}\n  cmd: {binary}\n  args:\n  - "{n}"\n  - {TARGET}/npusim_npu_config_v3_6_candidate.json\n  - {topo}\n  - {plans}/node_{n}.json\n  - full_layer\n  log: endpoint{n}.log\n  is_to_stdout: false\n  clock_rate: 1\n')
    yml.append(f'phase2:\n- role: noc\n  id: NOC\n  cmd: /usr/bin/python3\n  args:\n  - {ROOT}/network_packet.py\n')
    network=['-A','16','-c','1','-V','3','-B','8','-O','8','-F','4','-L','2000','-T','2000000','-r','1',
        '-I','../bench.txt','-R','4','-G',str(TARGET/'noc_mesh_4x4_v3_6_candidate.gv'),'-D','../delayInfo.txt','-P']
    yml+=['  - "'+v+'"\n' for v in network]
    yml.append('  log: network_driver.log\n  is_to_stdout: false\n  clock_rate: 1\nbench_file: ./bench.txt\ndelayinfo_file: ./delayInfo.txt\n')
    config=case/'test.yml';config.write_text(''.join(yml))
    files=[*ROOT.glob('*.py'),*ROOT.glob('*.md'),*ROOT.glob('capacity*.json'),ROOT/'hb_contract.json',
        Path('/mnt/sda1/h4567/v3_6_candidate_20260921/target_architecture_v3_6_candidate.yaml'),*plans.iterdir(),
        config,core,binary,ram,ROOT/'noc/build/popnet_cs_ni',topo,clocks_path,
        TARGET/'npusim_npu_config_v3_6_candidate.json',TARGET/'noc_mesh_4x4_v3_6_candidate.gv',
        TARGET/'ramulator2_hb_partition_v3_6_candidate.yaml']
    files.append(work/'all_off.cfg')
    for component in ('core','noc','npu'):
        files.extend(p for p in (ROOT/component).rglob('*') if p.is_file() and 'build' not in p.parts and p.suffix in ('.h','.cpp','.cc','.txt'))
    (case/'input_hashes.json').write_text(json.dumps({str(p):sha(p) for p in files if p.is_file()},indent=2))
    states=('vertices','ring_prediction_bounds','kernel_events','kernel_sram_service','exchange_sram_service','sram_service',
        'communication','local_events','native_tensor_dma','packing_sram_service','native_mac_events','posted_descriptors','reports/dram_transactions')
    env=dict(os.environ,SIMULATOR_ROOT=str(SIM),BENCHMARK_ROOT=str(ROOT),NPU_SRAM_NOC_PROFILE=str(profile),
        LEGOSIM_REQUIRE_MESSAGE_FIXED_POINT='1',LEGOSIM_TAGGED_NOC_REPLIES='1',LEGOSIM_ABSOLUTE_NOC_COMPLETIONS=str(int(args.predictor=='absolute')),
        LEGOSIM_RENDEZVOUS_FLIT_BYTES='32',
        LEGOSIM_HB_SERVICE_BYTES='128',LEGOSIM_HB_SERVICE_CYCLES='5',
        LEGOSIM_SHARED_PORT_PREDICTION_BOUND='1',
        NPU_RECORD_MAC='1',RAMULATOR_GLOBAL_WALL_CLOCK='1',NPU_CAUSAL_TRACE='1',NPU_CAUSAL_DDR_TRACE='1')
    env['LEGOSIM_CASE_MODE']=args.mode
    env['LEGOSIM_FIXED_POINT_STATE_FILES']=';'.join(f'proc_r{{round}}_p1_t{n+16}/{s}.csv' for n in range(16) for s in states)
    env['LEGOSIM_FIXED_POINT_STATE_FILES']+=';'+ ';'.join('reports/ramulator2_ch%d.csv'%n for n in range(16))
    env['LEGOSIM_FIXED_POINT_STATE_FILES']+=';'+ ';'.join('proc_r{round}_p1_t%d/causal_program.txt'%(n+16) for n in range(16))
    env['LEGOSIM_FIXED_POINT_STATE_FILES']+=';'+ ';'.join('proc_r{round}_p1_t%d/causal_memory_program.txt'%(n+16) for n in range(16))
    command=['timeout','--signal=TERM','--kill-after=30s',str(args.timeout),str(core),str(config),
        '-w','4','-H','4','-f','4','-t',str(args.rounds),'-e','0.0005']
    if args.observer_only:command.append('--phase1-only')
    status.update(state='running',argv=command);save()
    rc=supervised_run(command,work,env,case/'launcher.log',case/'supervision.json');assert rc==0
    if args.observer_only:
        hashes=json.loads((case/'input_hashes.json').read_text());assert all(sha(Path(p))==h for p,h in hashes.items())
        status.update(state='observer_phase1_completed',application_performance_claim=False)
        save();raise SystemExit(0)
    rounds=sorted(work.glob('proc_r*_p2_t0'),key=lambda p:int(p.name.split('_')[1][1:]))
    assert rounds
    last=rounds[-1]
    assert json.loads((last/'source_audit.json').read_text())['passed']
    assert json.loads((last/'receive_ready_summary.json').read_text())['state']=='passed'
    hashes=json.loads((case/'input_hashes.json').read_text());assert all(sha(Path(p))==h for p,h in hashes.items())
    status.update(state='native_rounds_finished_pending_exact_application_audit',completed_rounds=len(rounds),
        final_feedback=str(last/'output_delayInfo.txt'),final_feedback_sha256=sha(last/'output_delayInfo.txt'),
        converged_message_in_log='Simulation cycle has converged;' in (case/'launcher.log').read_text())
except SystemExit:
    raise
except BaseException as e:status.update(state='failed',reason=str(e));raise
finally:status['elapsed_host_seconds']=time.monotonic()-started;save()
