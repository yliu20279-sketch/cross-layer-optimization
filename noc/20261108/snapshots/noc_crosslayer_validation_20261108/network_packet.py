"""Native phase-1 events -> actual finite handshake -> native network feedback."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from check_source import audit_source

ROOT=Path(__file__).resolve().parent
args=list(sys.argv[1:]);i=args.index('-I')+1;raw=Path(args[i]);original=raw.read_bytes()
rows=[tuple(map(int,l.split())) for l in original.decode().splitlines() if l.strip()]
assert rows and all(len(r)==6 and 1<r[4]<=1025 and r[5]>>48==0x4e4f for r in rows)
rows.sort();stable=Path('stable_input_bench.txt')
stable.write_text(''.join(' '.join(map(str,r))+'\n' for r in rows));args[i]=str(stable)
Path('raw_input_bench.txt').write_bytes(original)
rid=int(re.fullmatch(r'proc_r(\d+)_p2_t0',Path.cwd().name).group(1))
receive={};send={};calendar=[];services=0;actual_services=Counter();program=[];native_commands={};native_done={}
for n in range(16):
    actor=Path.cwd().parent/f'proc_r{rid}_p1_t{n+16}'
    text=(actor/f'endpoint{n}.log').read_text()
    native_read={int(d):(int(t),int(b)) for t,sx,sy,dx,dy,b,d in
        re.findall(r'\[INTERCMD\] READ (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)',text) if int(d)>>48==0x4e4f}
    posted={int(r['descriptor']):r for r in csv.DictReader((actor/'posted_descriptors.csv').open())}
    assert set(posted)==set(native_read)
    for r in csv.DictReader((actor/'communication.csv').open()):
        assert int(r['node'])==n
        desc=int(r['descriptor']);peer=int(r['peer']);b=int(r['bytes']);issue=int(r['issue'])
        native_commands[n,desc,int(r['role']=='send')]=issue
        native_done[n,desc,int(r['role']=='send')]=(int(r['done']),b)
        if r['role']=='receive':
            assert native_read.pop(desc)==(issue,b)
            p=posted[desc];assert int(p['post_cycle'])==issue and int(p['bytes'])==b and int(p['buffer'])==int(r['buffer'])
            key=(peer,n,desc);assert key not in receive;receive[key]=(issue,b)
            calendar.append(f'post {n} {peer} {desc} {issue} {b} {r["buffer"]}\n')
            calendar.append(f'descriptor {n} {desc} {p["metadata_address"]}\n')
        else:
            assert r['role']=='send';key=(n,peer,desc);assert key not in send;send[key]=(issue,b)
    assert not native_read
    for name in ('kernel_sram_service','exchange_sram_service','sram_service','packing_sram_service'):
        path=actor/f'{name}.csv'
        if not path.exists():continue
        for r in csv.DictReader(path.open()):
            assert int(r.get('node',n))==n
            assert int(r['address'])+int(r['bytes'])<=4063232,'native access overlaps grant table'
            calendar.append(f'use {n} {r["time"]} {r["bytes"]}\n');services+=1
            actual_services[n,int(r['time']),int(r['bytes'])]+=1
assert len(receive)==len(send)==len(rows)
for ts,td,s,d,flits,desc in rows:
    assert send[s,d,desc]==(ts,(flits-1)*32) and receive[s,d,desc]==(td,(flits-1)*32)
cal=Path('receive_calendar.txt');cal.write_text(''.join(calendar))
traced_services=Counter();traced_commands={};wait_count=0
for n in range(16):
    actor=Path.cwd().parent/f'proc_r{rid}_p1_t{n+16}';bases={0:0};current=0
    for line in (actor/'causal_program.txt').read_text().splitlines():
        v=line.split();assert int(v[1])==n;f=int(v[2])
        if v[0]=='service':
            assert len(v)==6 and f==current
            off,b,time=map(int,v[3:]);assert time==bases[f]+off and off>0
            traced_services[n,time,b]+=1
        elif v[0]=='release':
            assert len(v)==6 and f==current
            desc,send,off=map(int,v[3:]);key=n,desc,send
            assert key not in traced_commands and off>=0
            traced_commands[key]=bases[f]+off
        else:
            assert v[0]=='fence' and len(v)==8 and f==current+1
            parent,gap,tx,rx,after=map(int,v[3:]);assert parent==current and gap>=0 and (tx or rx)
            before=bases[parent]+gap;expected=[before]
            if tx:expected.append(native_done[n,tx,1][0])
            if rx:expected.append(native_done[n,rx,0][0])
            if tx and rx:
                assert native_done[n,tx,1][1]==native_done[n,rx,0][1]==32768
                expected.append(before+2050)
            assert after==max(expected),(n,f,before,after,expected)
            bases[f]=after;current=f;wait_count+=1
        program.append(line+'\n')
assert actual_services==traced_services,'actual native SRAM callback records must match legacy observers exactly'
assert native_commands==traced_commands,'actual issued commands must match SDK/communication records exactly'
Path('explicit_program.txt').write_text(''.join(program))
Path('explicit_program_proof.json').write_text(json.dumps({'state':'passed','actual_SRAM_edges':services,
    'actual_blocking_waits':wait_count,'actual_commands':len(native_commands),'all_commands_and_services_independently_matched':True},indent=2))
from prepare_memory_program import prepare
memory_proof=prepare(rid,16,actual_services,native_commands)
Path('calendar_proof.json').write_text(json.dumps({'messages':len(rows),'actual_local_SRAM_edges':services,
    'original_message_multiset_unchanged':Counter(rows)==Counter(tuple(map(int,l.split())) for l in original.decode().splitlines() if l.strip()),
    'source':'actual native READ/WRITE, explicit stored descriptors, and exact local SRAM records',
    'calendar_sha256':hashlib.sha256(cal.read_bytes()).hexdigest()},indent=2))
env={k:v for k,v in os.environ.items() if not k.startswith('NOC_')}
configuration=Path.cwd().parent/'all_off.cfg'
if os.getenv('LEGOSIM_CASE_MODE')=='static_cs':
    configuration=Path('active_topology.cfg').resolve()
    routes=[f'route {i} {s} {d} 0\n' for i,(_,_,s,d,_,_) in enumerate(rows) if s in (0,3) and d==5]
    assert routes,'fixed-CS correctness test must exercise an actual routed flow'
    configuration.write_text((Path.cwd().parent/'all_off.cfg').read_text()+''.join(routes))
    Path('static_cs_rule.json').write_text(json.dumps({'scope':'fixed preconfigured circuit correctness only, not optimized/HiBand performance',
        'CS':0,'TX_node':0,'RX_node':5,'source_gateway_rule':'source 0 or 3 to destination 5 via gateway 0',
        'routed_messages':len(routes),'physical_configuration_changes_during_run':False},indent=2))
env.update(NOC_DATA_WIRE='1',NOC_AUX_CONFIG=str(configuration.resolve()),NOC_AUX_LOG='events.csv',
    NOC_SOURCE_CAPACITY_FLITS='1025',NOC_SOURCE_LOG='source.csv',NOC_RECEIVE_POSTS=str(cal.resolve()),
    NOC_SRAM_POLICY='npu_first',NOC_ROUTER_STALL_LOG='router_stalls',NOC_RECEIVE_READY='1',NOC_QUIESCENT_SKIP='0')
env.update(NOC_PROGRAM_FENCES=str(Path('explicit_memory_program.txt').resolve()),NOC_DRAM_PROGRAM='1',
    NOC_DRAM_CONFIG='/mnt/sda1/h4567/qwen15_moe_target_v36_20261009/ramulator2_hb_partition_v3_6_candidate.yaml',
    NOC_EMPTY_SKIP='1',NOC_IDLE_ROUTER_FAST='1',NOC_CAUSAL_COMMAND_CLOCK='1',
    NOC_STABLE_EVENT_ORDER='2',NOC_CLOCKED_SOURCE_ADMISSION='1')
binary=ROOT/'noc/build/popnet_cs_ni'
proof=json.loads((ROOT/'build_validation_status.json').read_text())
assert proof['state']=='protocol_units_passed' and hashlib.sha256(binary.read_bytes()).hexdigest()==proof['binary_sha256']
args[args.index('-T')+1]=str(max(max(r[0],r[1]) for r in rows)+4000000)
cp=subprocess.run([str(binary),*args],env=env,timeout=43200)
if cp.returncode:sys.exit(cp.returncode)
shutil.copy2('../delayInfo.txt','output_delayInfo.txt')
commands={}
altered=0
for r in csv.DictReader(Path('causal_command_times.csv').open()):
    key=int(r['node']),int(r['descriptor']),int(r['send'])
    assert key not in commands
    commands[key]=int(r['actual'])
    altered+=int(r['actual'])!=int(r['nominal'])
effective=[]
for ts,td,s,d,flits,desc in rows:
    effective.append((commands[s,desc,1],commands[d,desc,0],s,d,flits,desc))
assert len(commands)==2*len(rows)
Path('effective_input_bench.txt').write_text(''.join(' '.join(map(str,r))+'\n' for r in sorted(effective)))
Path('causal_command_audit.json').write_text(json.dumps({'state':'passed','commands':len(commands),
    'altered_request_timestamps':altered,'numerical_iteration_only':True,'all_original_messages_retained':True,
    'must_be_zero_before_performance_acceptance':True},indent=2))
b=json.loads(Path('bridge_summary.json').read_text());expected=sum(r[4] for r in rows)
assert b['completed_packets']==len(rows) and b['written_flits']==expected
assert b['payload_written_flits']==expected-len(rows) and b['control_retired_flits']==len(rows)
if os.getenv('LEGOSIM_CASE_MODE')=='static_cs':
    assert b['aux_written']==b['aux_sent']==b['aux_credits_returned']>0
    assert b['aux_written']+b['mesh_written']==expected
proof=audit_source('source.csv','output_delayInfo.txt');assert proof['source_flits']==expected
Path('source_audit.json').write_text(json.dumps(proof,indent=2))
assert json.loads(Path('receive_summary.json').read_text())['completed_posts']==len(rows)
assert json.loads(Path('receive_ready_summary.json').read_text())['data_admissions']==len(rows)
# NPU-first: do not feed old NI reservations back into NPU scheduling. They
# are measured service events, not advance reservations against computation.
