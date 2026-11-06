"""Read-only audit of existing controlled traces. No simulator/network calls."""
from pathlib import Path
import csv,json,hashlib,struct,shutil,math
from datetime import datetime,timezone,timedelta

OUT=Path(__file__).resolve().parent
ROOT=OUT.parent
SRC=ROOT/'qwen3_strategy_native_v1/evidence_v1'
manifest=json.loads((SRC/'manifest.json').read_text())
hashbytes=lambda b:hashlib.sha256(b).hexdigest()
def rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def save(name,v):(OUT/name).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def csvsave(name,rr):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
bound=[]
def bind(rel):
    p=SRC/rel;data=p.read_bytes();h=hashbytes(data)
    assert manifest[rel]==h,('original manifest mismatch',rel)
    dst=OUT/'source_snapshot'/rel;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(data)
    bound.append(dict(path=str(p),snapshot=str(dst.relative_to(OUT)),sha256=h,bytes=len(data)))
    return p
ops=rows(bind('graphs/coaccess_witness/ops.csv'));op={int(r['id']):r for r in ops}
deps=rows(bind('graphs/coaccess_witness/deps.csv'))
bind('graphs/coaccess_witness/modes.csv')
bind('runtime/coupled_main.cc');bind('frame_mapper.h');bind('protocol.json')
parents={i:[] for i in op}
for e in deps:parents[int(e['dst'])].append(int(e['src']))
assert parents[12]==list(range(12)) and 12 in parents[13]
logical_pages={i:int(op[i]['address'])//4096 for i in (0,1)}
assert logical_pages=={0:23360,1:23376}
transactions=[];operations=[];consumers=[];results={};allchecks=[]
launches={}
for strategy in ('rr','coaccess'):
    base=f'runs/coaccess_witness_{strategy}'
    tx=rows(bind(base+'/bank_requests.csv'))
    ev={int(r['id']):r for r in rows(bind(base+'/events.csv'))}
    run=json.loads(bind(base+'/run_manifest.json').read_text())
    launch=json.loads(bind(base+'/launch.json').read_text());launches[strategy]=launch
    q=struct.unpack('<131072I',bind(f'coaccess_witness_{strategy}.bin').read_bytes())
    assert len(set(q))==131072 and min(q)==0 and max(q)==131071
    inverse={v:i for i,v in enumerate(q)}
    assert set(ev)==set(op) and run['status']=='PASS' and run['causal_violations']==0
    for f in ('ops.csv','deps.csv','modes.csv'):
        assert launch['graph_hashes'][f]==hashbytes((SRC/'graphs/coaccess_witness'/f).read_bytes())
    assert launch['table_sha256']==hashbytes((SRC/f'coaccess_witness_{strategy}.bin').read_bytes())
    seen=set();byop={};logical=[]
    for r in tx:
        i=int(r['op_id']);a=int(r['address']);offset=a%4096
        logical_addr=inverse[a//4096]*4096+offset
        byteoff=logical_addr-int(op[i]['address'])
        assert i in op and op[i]['kind']=='LOAD' and byteoff in range(0,4096,256)
        assert (i,byteoff) not in seen;seen.add((i,byteoff))
        assert int(r['request_bytes'])==float(r['represented_bytes'])==256
        assert int(r['bankgroup'])==(a>>14)&3 and int(r['bank'])==(a>>16)&3
        assert int(r['row'])==a>>18 and int(r['column'])==(a>>8)&63
        assert int(r['inference_request_id'])==int(op[i]['inference_request_id'])
        assert float(r['submit_cycle'])<=float(r['callback_cycle'])<=float(ev[i]['done'])
        assert float(r['controller_arrive_tick'])<=float(r['first_issue_tick'])<=float(r['final_issue_tick'])<=float(r['controller_depart_tick'])
        byop.setdefault(i,[]).append((byteoff,r))
        logical.append((i,byteoff,logical_addr,int(r['request_bytes']),int(r['inference_request_id'])))
        if i in (0,1):
            transactions.append(dict(strategy=strategy,op=i,logical_page=logical_pages[i],logical_offset=byteoff,
             physical_frame=a//4096,decoded_bank=4*int(r['bankgroup'])+int(r['bank']),row=int(r['row']),column=int(r['column']),
             owner=int(r['inference_request_id']),submit_cycle=float(r['submit_cycle']),callback_cycle=float(r['callback_cycle']),
             arrive_tick=float(r['controller_arrive_tick']),first_issue_tick=float(r['first_issue_tick']),final_issue_tick=float(r['final_issue_tick']),
             depart_tick=float(r['controller_depart_tick']),queue_ticks=float(r['controller_queue_ticks']),
             cross_owner_bank_wait_ticks=float(r['cross_request_bank_wait_ticks']),row_status=r['row_status'],
             row_command_ticks=float(r['row_command_ticks']),completion_ticks=float(r['completion_ticks'])))
    for i,r in op.items():
        e=ev[i];assert float(e['ready'])<=float(e['start'])<=float(e['done'])
        assert all(float(ev[p]['done'])<=float(e['ready']) for p in parents[i])
        if r['kind']=='LOAD':
            rr=sorted(byop[i]);assert len(rr)==16 and [v[0] for v in rr]==list(range(0,4096,256))
            assert all(float(a[1]['callback_cycle'])<=float(b[1]['submit_cycle']) for a,b in zip(rr,rr[1:]))
            last=max(float(v['callback_cycle']) for _,v in rr)
            assert last==float(e['backend_done'])
            assert float(e['done'])==math.ceil(max(last,float(e['modeled_gate'])))
    assert len(tx)==3072 and sum(int(r['request_bytes']) for r in tx)==786432
    for i in (0,1,11):
        rr=byop[i];e=ev[i]
        operations.append(dict(strategy=strategy,op=i,task=op[i]['task'],logical_page=int(op[i]['address'])//4096,
          ready_cycle=float(e['ready']),start_cycle=float(e['start']),backend_done_cycle=float(e['backend_done']),
          modeled_gate_cycle=float(e['modeled_gate']),done_cycle=float(e['done']),
          cross_owner_bank_wait_ticks=sum(float(v['cross_request_bank_wait_ticks']) for _,v in rr)))
    for i in (12,13):
        e=ev[i];consumers.append(dict(strategy=strategy,op=i,task=op[i]['task'],parents=';'.join(map(str,parents[i])),
          ready_cycle=float(e['ready']),start_cycle=float(e['start']),done_cycle=float(e['done'])))
    assert max(float(ev[p]['done']) for p in parents[12])==float(ev[12]['ready'])
    assert float(ev[12]['done'])==float(ev[13]['ready'])
    results[strategy]=dict(cycles=run['total_cycles'],operations=run['operations'],dependencies=run['dependencies'],
       transaction_count=len(tx),logical=sorted(logical),first_window_latest_parent=max(range(12),key=lambda i:float(ev[i]['done'])),
       barrier_ready=float(ev[12]['ready']),barrier_done=float(ev[12]['done']),next_window_ready=float(ev[13]['ready']))
    allchecks.append(dict(strategy=strategy,original_manifest_binding=True,full_domain_bijection=True,
       all_3072_logical_transactions_and_callbacks=True,all_208_event_dependencies=True,
       mlp1_continuation=True,callback_to_op_done_rule=True,barrier_and_next_window_gate=True))
assert results['rr']['logical']==results['coaccess']['logical']
controls={s:{k:v for k,v in l['controls'].items() if k not in ('POPNET_STATS_DIR','HB_OUT','HB_FRAME_MAP_BIN')} for s,l in launches.items()}
assert controls['rr']==controls['coaccess']
normalized_commands={}
for s,l in launches.items():
    cmd=l['command'].copy();cmd[cmd.index('-I')+1]='<verified-empty-trace>'
    assert bind(f'runs/coaccess_witness_{s}/empty.trace').stat().st_size==0
    normalized_commands[s]=cmd
assert normalized_commands['rr']==normalized_commands['coaccess']
for result in results.values():result.pop('logical')
csvsave('PAIR_ALL_TRANSACTIONS.csv',transactions)
csvsave('PAIR_OFFSET256.csv',[r for r in transactions if r['logical_offset']==256])
csvsave('PAGE_OPERATIONS.csv',operations);csvsave('DEPENDENCY_PROPAGATION.csv',consumers)
def get(s,i,offset):return next(r for r in transactions if r['strategy']==s and r['op']==i and r['logical_offset']==offset)
a,b=get('rr',0,256),get('rr',1,256)
ac,bc=get('coaccess',0,256),get('coaccess',1,256)
assert a['decoded_bank']==b['decoded_bank']==0 and ac['decoded_bank']==0 and bc['decoded_bank']==1
overlap=lambda x,y:max(0,min(x['callback_cycle'],y['callback_cycle'])-max(x['submit_cycle'],y['submit_cycle']))
assert overlap(a,b)>0 and overlap(ac,bc)>0
assert (b['submit_cycle'],b['arrive_tick'],b['row'],b['column'],b['row_status'],b['row_command_ticks'],b['completion_ticks'])==(bc['submit_cycle'],bc['arrive_tick'],bc['row'],bc['column'],bc['row_status'],bc['row_command_ticks'],bc['completion_ticks'])
assert b['cross_owner_bank_wait_ticks']==120 and bc['cross_owner_bank_wait_ticks']==0
counter=get('rr',1,0);counter_ca=get('coaccess',1,0)
assert counter['cross_owner_bank_wait_ticks']==13 and counter_ca['cross_owner_bank_wait_ticks']==0
assert counter['callback_cycle']==counter_ca['callback_cycle']==50
gain=100*(results['rr']['cycles']-results['coaccess']['cycles'])/results['rr']['cycles']
save('EVIDENCE_CHAIN.json',dict(
 scope='CONTROLLED_SYNTHETIC_GROUP_LEVEL_OBSERVATIONAL_CHAIN_NOT_ISOLATED_PAIR_CAUSAL_EFFECT',
 experiment='qwen3_strategy_native_v1/evidence_v1 coaccess_witness',
 baseline='RR, not O_preRR or the previously cited eC O_fixture experiment',
 pair=dict(ops=[0,1],logical_pages=[23360,23376],local_pages=[0,16],offset_bytes=256,
   rr_same_bank=True,ca_different_banks=True,rr_outstanding_overlap_cycles=overlap(a,b),ca_outstanding_overlap_cycles=overlap(ac,bc),
   op1_wait_ticks_before=b['cross_owner_bank_wait_ticks'],op1_wait_ticks_after=bc['cross_owner_bank_wait_ticks'],
   op1_callback_cycle_before=b['callback_cycle'],op1_callback_cycle_after=bc['callback_cycle']),
 group=results,cycle_gain_percent=gain,checks=allchecks,
 counterexample=dict(op=1,offset=0,bank_wait_ticks_before=13,bank_wait_ticks_after=0,callback_before=50,callback_after=50),
 attribution_limits=['Other ten pages in window also change; no pair-only intervention',
  'No logged blocking transaction ID; the wait counter is cross-owner same-Bank, not pair-exclusive',
  'Row state and scheduling may change globally despite matching selected transaction row/column/status',
  'Consumer is explicit synthetic barrier over 12 LOADs; next consumer is another synthetic window',
  'Owners are synthetic labels, not real independent users; MLP=1 per op; not natural full-MoE gain'],
 no_new_simulation=True,no_remote_access=True))
save('SOURCE_MANIFEST.json',dict(time=datetime.now(timezone(timedelta(hours=8))).isoformat(),
 original_manifest_sha256=hashbytes((SRC/'manifest.json').read_bytes()),files=bound))
save('ORIGINAL_EC_PAIR_STATUS.json',dict(original_case='qwen3_eC',original_pair=[23378,23442],
 static_map_known=True,original_CA_bank_requests_local_file_present=(ROOT/'selector_execution_objective_v1/runs/qwen3_eC/coaccess/bank_requests.csv').exists(),
 conclusion='Not claimed as a closed transaction-level chain. No witness logs substituted for eC.'))
print(json.dumps(dict(status='PASS_CONTROLLED_TRACE_CHAIN_SCOPED',output=str(OUT),gain_percent=gain,
 original_manifest_files_verified=len(bound),pair_before=a,pair_B_before=b,pair_A_after=ac,pair_B_after=bc,
 results=results),ensure_ascii=False))
