from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import csv,datetime,hashlib,json,os,subprocess
from supervise import supervised_run
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
TARGET=Path('/mnt/sda1/h4567/qwen15_moe_target_v36_20261009')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(mode):
    case=ROOT/mode;case.mkdir(exist_ok=False);work=case/'run';work.mkdir();profile=work/'profile';profile.mkdir()
    for n in range(16):(profile/f'node_{n}.txt').write_text('')
    (work/'reports').mkdir()
    (work/'delayInfo.txt').write_text('');(work/'delayInfo.txt.predictions').write_text('')
    (work/'all_off.cfg').write_text('params 2 1 1 3 1\n'+''.join(f'cs {i} 0\n' for i in range(9))+''.join(f'node {i} 0 0\n' for i in range(16)))
    y=['phase1:\n']
    for n in range(16):
        y.append(f'- cmd: {ROOT}/npu/build/short_chain\n  args:\n  - "{n}"\n  - {TARGET}/npusim_npu_config_v3_6_candidate.json\n  log: endpoint{n}.log\n  is_to_stdout: false\n  clock_rate: 1\n')
    ram=BASE/'ramulator_wallclock_20261107/build/ramulator2'
    for n in range(16):
        y.append(f'- cmd: {ram}\n  args:\n  - "{n%4}"\n  - "{4+n//4}"\n  - "1.25"\n  - --server\n  - {TARGET}/ramulator2_hb_partition_v3_6_candidate.yaml\n  - "2147483648"\n  - "1"\n  - ../reports/ramulator2_ch{n}.csv\n  log: dram{n}.log\n  is_to_stdout: false\n  clock_rate: 1\n')
    y.append(f'phase2:\n- cmd: /usr/bin/python3\n  args:\n  - {ROOT}/network.py\n')
    args=['-A','16','-c','1','-V','3','-B','8','-O','8','-F','4','-L','2000','-T','200000','-r','1','-I','../bench.txt','-R','4','-G',str(TARGET/'noc_mesh_4x4_v3_6_candidate.gv'),'-D','../delayInfo.txt','-P']
    y+=['  - "'+a+'"\n' for a in args];y.append('  log: network_driver.log\n  is_to_stdout: false\n  clock_rate: 1\nbench_file: ./bench.txt\ndelayinfo_file: ./delayInfo.txt\n')
    config=case/'test.yml';config.write_text(''.join(y))
    core=ROOT/'core/build/interchiplet'
    env=dict(os.environ,SIMULATOR_ROOT=str(BASE/'LEGOSIM_NPU_R2_V20260831'),BENCHMARK_ROOT=str(ROOT),
        NPU_SRAM_NOC_PROFILE=str(profile),LEGOSIM_TAGGED_NOC_REPLIES='1',LEGOSIM_RENDEZVOUS_FLIT_BYTES='32',
        LEGOSIM_ABSOLUTE_NOC_COMPLETIONS=str(int(mode=='absolute')),LEGOSIM_REQUIRE_MESSAGE_FIXED_POINT='1',UNIT_PROGRAM_FENCES='1',RAMULATOR_GLOBAL_WALL_CLOCK='1',
        LEGOSIM_HB_SERVICE_BYTES='128',LEGOSIM_HB_SERVICE_CYCLES='5',NPU_CAUSAL_TRACE='1',NPU_CAUSAL_DDR_TRACE='1')
    env['LEGOSIM_FIXED_POINT_STATE_FILES']=';'.join(f'proc_r{{round}}_p1_t{n}/{s}.csv' for n in range(16) for s in ('local_events','sram_service','communication','exchange_sram_service','posted_descriptors','join_bounds','gate_events'))
    env['LEGOSIM_FIXED_POINT_STATE_FILES']+=';'+ ';'.join(f'proc_r{{round}}_p1_t{n}/causal_memory_program.txt' for n in range(16))
    env['LEGOSIM_FIXED_POINT_STATE_FILES']+=';'+ ';'.join(f'proc_r{{round}}_p1_t{n}/reports/dram_transactions.csv' for n in range(16))
    env['LEGOSIM_FIXED_POINT_STATE_FILES']+=';'+ ';'.join(f'reports/ramulator2_ch{n}.csv' for n in range(16))
    rc=supervised_run(['timeout','--signal=TERM','--kill-after=20s','900',str(core),str(config),'-w','4','-H','4','-f','4','-t','16','-e','0.0005'],work,env,case/'launcher.log',case/'supervision.json')
    dirs=sorted(work.glob('proc_r*_p2_t0'),key=lambda p:int(p.name.split('_')[1][1:]));last=dirs[-1]
    result={'mode':mode,'exit':rc,'rounds':len(dirs),'converged':'Simulation cycle has converged;' in (case/'launcher.log').read_text(),'scope':'short native vector/DMA/DDR chain with actual NI configuration packets; not Qwen performance'}
    assert rc==0 and result['converged'],result
    if result['converged']:
        assert len(dirs)>=2 and sha(last/'output_delayInfo.txt')==sha(dirs[-2]/'output_delayInfo.txt')
        actual={v[3]:(v[0],v[0]+v[5],v[0]+v[6]) for l in (last/'output_delayInfo.txt').read_text().splitlines() if (v:=list(map(int,l.split())))}
        r=int(last.name.split('_')[1][1:])
        for n in range(16):
            with (work/f'proc_r{r}_p1_t{n}'/'communication.csv').open() as h:
                for v in csv.DictReader(h):assert int(v['done'])==actual[int(v['descriptor'])][1 if v['role']=='send' else 2]
        result['predicted_equals_actual_every_completion']=True
        for solved in dirs[-2:]:
            commands=list(csv.DictReader((solved/'causal_command_times.csv').open()))
            assert len(commands)==96 and all(v['nominal']==v['actual'] for v in commands)
            guide=json.loads((solved/'program_fences_summary.json').read_text())
            assert guide['retimed_services']==guide['release_deferrals']==0
            assert guide['retimed_DRAM_completions']==0 and guide['actual_native_DRAM_requests']==64
            assert json.loads((solved/'dynamic_interface_validation.json').read_text())['state']=='passed'
        result['last_two_rounds_zero_numerical_guidance']=True
        for n in range(16):
            d=list(csv.DictReader((work/f'proc_r{r}_p1_t{n}/reports/dram_transactions.csv').open()))
            assert len(d)==4 and all(int(v['external_elapsed_cycles'])>0 for v in d)
            assert [v['label'] for v in d]==['short_source_materialization']*3+['short_result_writeback']
        for name in ('source.csv','events.csv','receive_events.csv','receive_ready_events.csv','wire_headers.csv','control_events.csv'):
            assert sha(last/name)==sha(dirs[-2]/name),('last raw states differ',name)
        result['actual_Ramulator_requests']=64
    (case/'result.json').write_text(json.dumps(result,indent=2));return result
state={'state':'starting','application_performance':False,'purpose':'short native chain/configuration integration; no 24-block requirement'}
def save():state['updated']=datetime.datetime.now().isoformat();(ROOT/'chain_status.json').write_text(json.dumps(state,indent=2))
save()
try:
    state['state']='running';save()
    with ProcessPoolExecutor(max_workers=2) as pool:state['cases']=list(pool.map(run,('absolute','relative')))
    state['state']='completed'
except BaseException as e:state.update(state='failed',reason=repr(e));raise
finally:save()
