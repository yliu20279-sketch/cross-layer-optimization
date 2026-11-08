"""Reference-byte regression plus independently summed observation counters."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json
import os
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent.parent
REFERENCE=BASE/'noc_quiescent_skip_v2_20261107'
TARGET=Path('/mnt/sda1/h4567/qwen15_moe_target_v36_20261009')
OUT=ROOT/'validation';OUT.mkdir(exist_ok=False)
status={'state':'running','cases':[],'application_performance_claim':False}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save():(ROOT/'validation_status.json').write_text(json.dumps(status,indent=2))
save();start=time.monotonic()
try:
    proof=json.loads((REFERENCE/'validated_skip.json').read_text());assert proof['state']=='passed'
    assert sha(REFERENCE/'build/popnet_cs_ni')==proof['binary_sha256']
    original=Path(proof['report']).parent
    fields=['events.csv','source.csv','wire_headers.csv','wire_summary.json','bridge_summary.json',
            'receive_events.csv','receive_summary.json','router_stalls.csv',
            'router_stalls_packets.csv','router_stalls_forwarded.csv']
    tasks=[]
    for item in sorted((original/'inputs').iterdir()):
        reference=original/'validation'/item.name/'enabled'
        tasks.append((item.name,item/'bench.txt',item/'receive_calendar.txt',
                      item/'topology.cfg' if (item/'topology.cfg').exists() else original/'all_off.cfg',
                      int((item/'deadline').read_text()),reference,reference/'delayInfo.txt'))
    real=BASE/'qwen15_bulk_moe_native_20261107/layer1_mesh/run/proc_r4_p2_t0'
    assert (real/'source_audit.json').is_file(),'real reference NoC round not yet complete'
    bench=real/'stable_input_bench.txt'
    deadline=max(max(map(int,line.split()[:2])) for line in bench.read_text().splitlines())+2000000
    tasks.append(('actual_first_layer_round4',bench,real/'receive_calendar.txt',
                  BASE/'qwen15_bulk_moe_native_20261107/all_off.cfg',deadline,real,real/'output_delayInfo.txt'))
    for name,bench,calendar,config,deadline,ref,ref_delay in tasks:
        case=OUT/name;case.mkdir()
        env={k:v for k,v in os.environ.items() if not k.startswith('NOC_')}
        env.update(NOC_DATA_WIRE='1',NOC_AUX_CONFIG=str(config),NOC_AUX_LOG='events.csv',
                   NOC_SOURCE_CAPACITY_FLITS='1025',NOC_SOURCE_LOG='source.csv',
                   NOC_RECEIVE_POSTS=str(calendar),NOC_SRAM_POLICY='noc_first',
                   NOC_ROUTER_STALL_LOG='router_stalls',NOC_QUIESCENT_SKIP='1')
        argv=[str(ROOT/'build/popnet_cs_ni'),'-A','16','-c','1','-V','3','-B','8','-O','8','-F','4','-L','2000',
              '-T',str(deadline),'-r','1','-I',str(bench),'-R','4',
              '-G',str(TARGET/'noc_mesh_4x4_v3_6_candidate.gv'),'-D','delayInfo.txt','-P']
        inputs={str(p):sha(p) for p in (bench,calendar,config,ref_delay)}
        before=time.monotonic()
        with (case/'run.log').open('w') as log:
            subprocess.run(argv,cwd=case,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1800,check=True)
        assert sha(case/'delayInfo.txt')==sha(ref_delay),(name,'delay')
        for field in fields:assert sha(case/field)==sha(ref/field),(name,field)
        assert all(sha(Path(p))==h for p,h in inputs.items())
        aggregate=Counter();packets=Counter();busy=Counter()
        for r in csv.DictReader((case/'router_stalls_forwarded.csv').open()):
            key=tuple(int(r[k]) for k in ('node','input_port','output_port'))
            aggregate[key]+=int(r['forwarded_flits'])
        for r in csv.DictReader((case/'router_stalls_packet_forwarded.csv').open()):
            key=tuple(int(r[k]) for k in ('node','input_port','output_port'))
            packets[key]+=int(r['forwarded_flits']);assert int(r['packet'])>=0
        assert packets==aggregate,'packet observer failed original-total conservation'
        previous={}
        for r in csv.DictReader((case/'router_stalls_forward_busy.csv').open()):
            n,a,b=int(r['node']),int(r['begin']),int(r['end'])
            assert a<b and a>previous.get(n,-1);previous[n]=b;busy[n]+=b-a
        for n,duration in busy.items():assert duration<=sum(v for (node,i,o),v in aggregate.items() if node==n)
        status['cases'].append({'name':name,'state':'passed',
                                'original_11_outputs_byte_exact':True,'packet_totals_match_original':True,
                                'forwarded_flits':sum(aggregate.values()),'host_seconds':time.monotonic()-before,
                                'input_sha256':inputs});save()
    status.update(state='passed',binary_sha256=sha(ROOT/'build/popnet_cs_ni'),
                  read_only_observation_validated=True,physical_timing_unchanged=True)
except BaseException as e:status.update(state='failed',reason=str(e));raise
finally:status['elapsed_host_seconds']=time.monotonic()-start;save()
