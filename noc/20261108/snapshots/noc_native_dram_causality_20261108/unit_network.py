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
receive={};send={};calendar=[];services=0;actual_services=Counter();native_commands={}
for n in range(16):
    actor=Path.cwd().parent/f'proc_r{rid}_p1_t{n}'
    text=(actor/f'endpoint{n}.log').read_text()
    native_read={int(d):(int(t),int(b)) for t,sx,sy,dx,dy,b,d in
        re.findall(r'\[INTERCMD\] READ (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)',text) if int(d)>>48==0x4e4f}
    posted={int(r['descriptor']):r for r in csv.DictReader((actor/'posted_descriptors.csv').open())}
    assert set(posted)==set(native_read)
    for r in csv.DictReader((actor/'communication.csv').open()):
        assert int(r['node'])==n
        desc=int(r['descriptor']);peer=int(r['peer']);b=int(r['bytes']);issue=int(r['issue'])
        native_commands[n,desc,int(r['role']=='send')]=issue
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
if os.getenv('UNIT_PROGRAM_FENCES')=='1':
    program=[]
    for n in range(16):
        actor=Path.cwd().parent/f'proc_r{rid}_p1_t{n}'
        with (actor/'join_bounds.csv').open() as h:joins=list(csv.DictReader(h))
        bases=[0]+[int(v['join']) for v in joins]
        for v in joins:
            step=int(v['step']);tx=0x4e4f000003000000|((step+1)<<20)|(n<<8)|((n+1)%16)
            rx=0x4e4f000003000000|((step+1)<<20)|(((n+15)%16)<<8)|n
            issue=int(v['issue']);gap=issue-bases[step];assert gap>=0
            program.append(f'fence {n} {step+1} {step} {gap} {tx} {rx} {bases[step+1]}\n')
            program.append(f'release {n} {step} {tx} 1 {gap}\n')
            program.append(f'release {n} {step} {rx} 0 {gap}\n')
        with (actor/'sram_service.csv').open() as h:
            for v in csv.DictReader(h):
                label=v['label']
                if label=='materialize_owned_chunk':fence=0
                elif label.startswith('tx_read_p3_s'):fence=int(label.split('_s')[-1])
                elif label.startswith('ag_copy_s'):fence=int(label.split('_s')[-1])+1
                else:raise ValueError(('unrecognized actual primitive',label))
                time=int(v['time']);off=time-bases[fence];assert off>0
                program.append(f'service {n} {fence} {off} {v["bytes"]} {time}\n')
        with (actor/'exchange_sram_service.csv').open() as h:
            for v in csv.DictReader(h):
                fence=int(v['op']);time=int(v['time']);off=time-bases[fence];assert off>0
                program.append(f'service {n} {fence} {off} {v["bytes"]} {time}\n')
    Path('explicit_program.txt').write_text(''.join(program))
from prepare_memory_program import prepare
prepare(rid,0,actual_services,native_commands)
Path('calendar_proof.json').write_text(json.dumps({'messages':len(rows),'actual_local_SRAM_edges':services,
    'original_message_multiset_unchanged':Counter(rows)==Counter(tuple(map(int,l.split())) for l in original.decode().splitlines() if l.strip()),
    'source':'actual native READ/WRITE, explicit stored descriptors, and exact local SRAM records',
    'calendar_sha256':hashlib.sha256(cal.read_bytes()).hexdigest()},indent=2))
env={k:v for k,v in os.environ.items() if not k.startswith('NOC_')}
env.update(NOC_DATA_WIRE='1',NOC_AUX_CONFIG=str((Path.cwd().parent/'all_off.cfg').resolve()),NOC_AUX_LOG='events.csv',
    NOC_SOURCE_CAPACITY_FLITS='1025',NOC_SOURCE_LOG='source.csv',NOC_RECEIVE_POSTS=str(cal.resolve()),
    NOC_SRAM_POLICY='npu_first',NOC_ROUTER_STALL_LOG='router_stalls',NOC_RECEIVE_READY='1',NOC_QUIESCENT_SKIP='0',
    NOC_CAUSAL_COMMAND_CLOCK='1',NOC_EMPTY_SKIP='1',NOC_IDLE_ROUTER_FAST='1',NOC_STABLE_EVENT_ORDER='2',NOC_CLOCKED_SOURCE_ADMISSION='1')
if os.getenv('UNIT_PROGRAM_FENCES')=='1':env['NOC_PROGRAM_FENCES']=str(Path('explicit_memory_program.txt').resolve())
env.update(NOC_DRAM_PROGRAM='1',NOC_DRAM_CONFIG='/mnt/sda1/h4567/qwen15_moe_target_v36_20261009/ramulator2_hb_partition_v3_6_candidate.yaml')
binary=ROOT/'noc/build/popnet_cs_ni'
proof=json.loads((ROOT/'build_validation_status.json').read_text())
assert proof['state']=='protocol_units_passed' and hashlib.sha256(binary.read_bytes()).hexdigest()==proof['binary_sha256']
args[args.index('-T')+1]=str(max(max(r[0],r[1]) for r in rows)+100000)
cp=subprocess.run([str(binary),*args],env=env,timeout=7200)
if cp.returncode:sys.exit(cp.returncode)
shutil.copy2('../delayInfo.txt','output_delayInfo.txt')
b=json.loads(Path('bridge_summary.json').read_text());expected=sum(r[4] for r in rows)
assert b['completed_packets']==len(rows) and b['written_flits']==expected
assert b['payload_written_flits']==expected-len(rows) and b['control_retired_flits']==len(rows)
proof=audit_source('source.csv','output_delayInfo.txt');assert proof['source_flits']==expected
Path('source_audit.json').write_text(json.dumps(proof,indent=2))
assert json.loads(Path('receive_summary.json').read_text())['completed_posts']==len(rows)
assert json.loads(Path('receive_ready_summary.json').read_text())['data_admissions']==len(rows)
# Numerical solver metadata only. Preserve every measured output byte in
# output_delayInfo.txt and keep the predictor sidecar separate from that data.
predictions={}
for n in range(16):
    actor=Path.cwd().parent/f'proc_r{rid}_p1_t{n}'
    for r in csv.DictReader((actor/'communication.csv').open()):
        peer=int(r['peer']);desc=int(r['descriptor']);s,d=(n,peer) if r['role']=='send' else (peer,n)
        v=predictions.setdefault((s,d,desc),{})
        v['write' if r['role']=='send' else 'read']=int(r['issue'])
        v['source_done' if r['role']=='send' else 'receive_done']=int(r['done'])
assert len(predictions)==len(rows)
sidecar=''.join(f'{desc} {s} {d} {v["write"]} {v["source_done"]} {v["receive_done"]}\n'
                for (s,d,desc),v in sorted(predictions.items()))
Path('numerical_predictions.txt').write_text(sidecar)
Path('../delayInfo.txt.predictions').write_text(sidecar)
# NPU-first: do not feed old NI reservations back into NPU scheduling. They
# are measured service events, not advance reservations against computation.
