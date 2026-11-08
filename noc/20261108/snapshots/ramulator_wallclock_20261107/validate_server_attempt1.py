"""Full target endpoint count, but explicit artificial protocol/clock unit."""
from pathlib import Path
import csv
import hashlib
import json
import os
import subprocess
import time
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'qwen15_native_suite_20261107'))
from supervise import supervised_run
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
TARGET=Path('/mnt/sda1/h4567/qwen15_moe_target_v36_20261009');SIM=BASE/'LEGOSIM_NPU_R2_V20260831'
OUT=ROOT/'server_unit';OUT.mkdir(exist_ok=False)
start=time.monotonic();status={'state':'building','cases':[],'artificial_protocol_unit':True,'Qwen_application_performance':False}
def save():(ROOT/'server_validation_status.json').write_text(json.dumps(status,indent=2))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
save()
try:
    assert json.loads((ROOT/'validated_backend.json').read_text())['state']=='passed'
    for name,argv in [('configure',['cmake','-S',str(ROOT),'-B',str(ROOT/'build'),'-DCMAKE_BUILD_TYPE=Release']),
                      ('build',['cmake','--build',str(ROOT/'build'),'-j','4'])]:
        with (OUT/(name+'.log')).open('w') as log:subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
    native=SIM/'Ramulator2-Chiplet/ramulator2';new=ROOT/'build/ramulator2'
    assert sha(new)==json.loads((ROOT/'validated_backend.json').read_text())['binary_sha256'],'candidate binary changed after its unit check'
    for label,binary,wall in [('original',native,False),('candidate_disabled',new,False),('candidate_wallclock',new,True)]:
        case=OUT/label;case.mkdir();work=case/'run';work.mkdir();(work/'reports').mkdir()
        lines=['phase1:\n']
        for n in range(16):
            lines.append('- role: dram_proxy\n  id: CH%d\n  cmd: %s\n  args:\n'%(n,binary))
            for arg in (str(n%4),str(4+n//4),'1.25','--server',str(TARGET/'ramulator2_hb_partition_v3_6_candidate.yaml'),
                        '2147483648','1','../reports/ramulator2_ch%d.csv'%n):lines.append('  - "%s"\n'%arg)
            lines.append('  log: ramulator2.ch%d.log\n  is_to_stdout: false\n  clock_rate: 1\n'%n)
        for n in range(16):
            lines.append('- role: npu\n  id: N%d\n  cmd: %s\n  args:\n'%(n,ROOT/'build/server_client'))
            for arg in (str(n),str(TARGET/'npusim_npu_config_v3_6_candidate.json')):lines.append('  - "%s"\n'%arg)
            lines.append('  log: client%d.log\n  is_to_stdout: false\n  clock_rate: 1\n'%n)
        lines.append('phase2: []\nbench_file: ./bench.txt\ndelayinfo_file: ./delayInfo.txt\n')
        config=case/'test.yml';config.write_text(''.join(lines))
        env=dict(os.environ,SIMULATOR_ROOT=str(SIM));env.pop('RAMULATOR_GLOBAL_WALL_CLOCK',None)
        if wall:env['RAMULATOR_GLOBAL_WALL_CLOCK']='1'
        argv=['timeout','--signal=TERM','--kill-after=20s','1800',str(BASE/'noc_absolute_fixedpoint_20261107/build/interchiplet'),
              str(config),'-w','4','-H','4','-f','4','-t','1','--phase1-only']
        status.update(state='running',active_case=label);save()
        assert supervised_run(argv,work,env,case/'launcher.log',case/'supervision.json')==0
        for n in range(16):
            actor=work/('proc_r1_p1_t%d'%(n+16));transactions=list(csv.DictReader((actor/'reports/dram_transactions.csv').open()))
            server=work/'reports'/('ramulator2_ch%d.csv'%n);raw=list(csv.DictReader(server.open()))
            assert len(raw)==len(transactions)==12
            assert [r['request_id'] for r in raw]==[r['request_id'] for r in transactions]
            if label=='candidate_disabled':
                old=OUT/'original/run'
                assert sha(server)==sha(old/'reports'/server.name)
                assert sha(actor/'reports/dram_transactions.csv')==sha(old/actor.name/'reports/dram_transactions.csv')
            if wall:
                joined=case/('joined_node%d.csv'%n)
                with joined.open('w',newline='') as f:
                    writer=csv.writer(f);writer.writerow(['arrival','address','bytes','write','start','end','done'])
                    prior_end=0
                    for a,b in zip(transactions,raw):
                        assert a['operation']==b['operation'] and a['bytes']==b['bytes']
                        t=int(b['service_start_cycle']);begin=int(b['dram_service_start_tick']);end=int(b['dram_service_end_tick'])
                        assert begin>=((4*t+4)//5) and begin>=prior_end
                        assert int(b['service_done_cycle'])==(5*end+3)//4
                        assert int(b['dram_idle_ticks'])==begin-prior_end;prior_end=end
                        writer.writerow([t,a['address'],a['bytes'],int(a['operation']=='STORE'),begin,end,b['service_done_cycle']])
                with (case/('reference_node%d.log'%n)).open('w') as log:
                    subprocess.run([str(ROOT/'build/replay_server_probe'),str(TARGET/'ramulator2_hb_partition_v3_6_candidate.yaml'),str(joined)],
                                   stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        status['cases'].append({'name':label,'state':'passed','actual_NPU_clients':16,'actual_Ramulator2_servers':16,
                                'DRAM_total_bytes':34359738368,'transactions':192,
                                'wallclock_checked_against_direct_engine':wall,
                                'disabled_byte_equivalent_to_original':label=='candidate_disabled'});save()
    status.update(state='passed',backend_binary_sha256=sha(new),
                  scope='16 endpoint/R2 native protocol clock unit; not Qwen application or NoC optimization performance')
except BaseException as e:status.update(state='failed',reason=str(e));raise
finally:status['elapsed_host_seconds']=time.monotonic()-start;save()
