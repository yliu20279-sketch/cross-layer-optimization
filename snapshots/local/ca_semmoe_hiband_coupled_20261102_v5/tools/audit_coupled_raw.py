"""Independent streaming audit of this run's raw callbacks and lifetimes.

Does not import the model executor, replay a simulator, or alter any output.
FNV checks are consistency fingerprints, not cryptographic payload equality.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import time

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--model',required=True,choices=['qwen3','qwen15'])
parser.add_argument('--tag',default='layer01');args=parser.parse_args()
R=ROOT/'runs'/(args.model+'_'+args.tag);B=R/'backend'
receipt=json.loads((R/'RESULT.json').read_text());summary=receipt['summary'];begin=time.monotonic()
changed_frames={};migration_start=migration_complete=None
if summary.get('mapping_installs',0):
    assert summary['mapping_installs']==1,'only the declared one-swap diagnostic is supported'
    protocol=json.loads((R/'MAPPING_PROTOCOL.json').read_text())
    events=[json.loads(line) for line in (B/'MAPPING_EVENTS.jsonl').read_text().splitlines()]
    assert len(events)==1 and protocol['changed_valid_bytes']==8192
    migration_start=events[0]['start'];migration_complete=events[0]['complete']
    for row in protocol['changed_rows_after']:
        obj,page,frame,rank=map(int,row);changed_frames[(obj,page)]=(frame,rank)
    assert len(changed_frames)==2
out=R/'INDEPENDENT_RAW_AUDIT.json';assert not out.exists(),'preserve existing audit'
lifes=list(csv.DictReader((B/'LIFETIMES.csv').open()));cursor=0
live={};regions=[{} for _ in range(16)];reserved=[0]*16;peak=[0]*16;writes={}
allocated=released=0
def life_until(now):
    global cursor,allocated,released
    while cursor<len(lifes) and int(lifes[cursor]['time'])<=now:
        row=lifes[cursor];cursor+=1
        obj,rank,address,valid,extent,generation=(int(row[k]) for k in ('object','rank','address','valid','reserved','generation'))
        assert 0<=rank<16 and 0<valid<=extent and extent%4096==0 and address%4096==0
        assert address+extent<=512*1024**2
        if row['event']=='allocate':
            assert obj not in live
            assert all(max(address,a)>=min(address+extent,a+n) for a,n in regions[rank].values())
            live[obj]=(rank,address,valid,extent,generation);regions[rank][obj]=(address,extent);writes[obj]={}
            reserved[rank]+=extent;peak[rank]=max(peak[rank],reserved[rank]);allocated+=1
        else:
            assert live.pop(obj)==(rank,address,valid,extent,generation)
            del regions[rank][obj];del writes[obj];reserved[rank]-=extent;released+=1
pending={};net=set();issued=completed=packets=packets_done=read_checks=unmatched_read_windows=0
migration_read_bytes=migration_write_bytes=0
hasher=hashlib.sha256();examples=[]
with (B/'LIVE_EVENTS.csv').open('rb') as f:
    header=next(f);hasher.update(header)
    for raw in f:
        hasher.update(raw);p=raw.rstrip().split(b',');kind=p[0];t=float(p[1]);serial=int(p[2])
        life_until(t)
        if kind in (b'DRAM_ISSUE',b'DRAM_DONE'):
            rank,address,n,write,obj,generation,value=(int(x) for x in p[3:10])
            assert obj in live
            rr,base,valid,extent,gg=live[obj]
            logical=int(p[10]) if len(p)>10 else address-base
            migration=int(p[11]) if len(p)>11 else 0
            assert (rank,generation)==(rr,gg) and 0<n<=256 and logical>=0
            assert logical+n<=(extent if migration else valid)
            if migration:
                assert migration_start is not None and migration_start<=t<=migration_complete
                assert (obj,logical//4096) in changed_frames
                allowed={base//4096+page for oo,page in changed_frames if oo==obj}
                allowed|={frame for (oo,page),(frame,rrr) in changed_frames.items() if oo==obj}
                assert address//4096 in allowed
            else:
                expected_frame=base//4096+logical//4096
                if migration_complete is not None and t>=migration_complete and (obj,logical//4096) in changed_frames:
                    expected_frame,owner=changed_frames[(obj,logical//4096)];assert owner==rank
                assert address==expected_frame*4096+logical%4096,'actual physical address differs from declared live map'
            assert address%4096+n<=4096
            identity=(rank,address,n,write,obj,generation)
            if kind==b'DRAM_ISSUE':
                assert serial==issued and serial not in pending
                pending[serial]=(t,identity,value);issued+=1
            else:
                st,expected,old_value=pending.pop(serial)
                assert t>=st and expected==identity
                key=(int(p[10]) if len(p)>10 else address-base,n)
                if write:
                    assert value==old_value;writes[obj][key]=value
                    if migration:migration_write_bytes+=n
                elif key in writes[obj]:
                    assert writes[obj][key]==value,('actual read differs from completed write',serial,obj,key)
                    read_checks+=1
                    if migration:migration_read_bytes+=n
                else:
                    unmatched_read_windows+=1
                    if len(examples)<10:examples.append({'object':obj,'offset':address-base,'bytes':n})
                completed+=1
        elif kind==b'NOC_ISSUE':
            assert serial==packets and serial not in net;net.add(serial);packets+=1
        elif kind==b'NOC_DONE':
            net.remove(serial);packets_done+=1
        else:raise AssertionError(('unknown raw event',kind))
life_until(float('inf'))
assert not pending and not net and not live and not any(reserved) and allocated==released
assert issued==completed==summary['transactions']==summary['callbacks']
assert packets==packets_done==summary['packets']==summary['packet_callbacks']
assert peak==summary['HB_peak_reserved']
assert migration_write_bytes==summary.get('migration_write_bytes',0)
jobs={};tiles=0
for filename in ('LOWERING.jsonl','VECTOR_LOWERING.jsonl'):
    for line in (B/filename).open():
        row=json.loads(line);job=row['job'];assert job not in jobs
        assert row['begin']<=row['last_reader']<=row['complete'];jobs[job]=row
assert set(jobs)==set(range(1,summary['jobs']+1))
last={}
for row in csv.reader((B/'MATRIX_TILES.csv').open()):
    job,version,n0,st,ready,reader,done=map(int,row)
    assert job in jobs and st<=ready<=reader<=done<=jobs[job]['complete']
    if job in last:
        vv,prior_reader=last[job];assert version==vv+1 and prior_reader<=st
    else:assert version==1
    last[job]=(version,reader);tiles+=1
prefill=json.loads((R/'prefill_KV_PAYLOADS.json').read_text())
decode=json.loads((R/'decode_KV_PAYLOADS.json').read_text());bykey={(e['rank'],e['member']):e for e in decode}
prefix_checks=0
for entry in prefill:
    following=bykey[(entry['rank'],entry['member'])]
    old=(R/entry['file']).read_bytes();new=(R/following['file']).read_bytes()
    assert hashlib.sha256(old).hexdigest()==entry['sha256'] and hashlib.sha256(new).hexdigest()==following['sha256']
    assert following['length']==2 and entry['length']==1 and new[:len(old)]==old
    prefix_checks+=1
result={'status':'PASS_INDEPENDENT_LIVE_CALLBACK_LIFETIME_AND_KV_AUDIT_ONLY',
    'model':args.model,'transactions':issued,'packets':packets,'allocations':allocated,'releases':released,
    'read_windows_matching_completed_write_fingerprints':read_checks,'unmatched_read_windows':unmatched_read_windows,
    'unmatched_examples':examples,'fingerprint_algorithm':'FNV64 noncryptographic; not full numeric oracle',
    'primitive_jobs':len(jobs),'matrix_tiles':tiles,'KV_prefix_payloads_checked':prefix_checks,
    'migration_read_bytes':migration_read_bytes,'migration_write_bytes':migration_write_bytes,
    'raw_event_bytes':(B/'LIVE_EVENTS.csv').stat().st_size,'raw_event_sha256':hasher.hexdigest(),
    'HB_peak_reserved':peak,'elapsed_seconds':time.monotonic()-begin,
    'model_oracle_verified':False,'formal_performance_runs':0}
out.write_text(json.dumps(result,indent=2))
print(json.dumps(result))
