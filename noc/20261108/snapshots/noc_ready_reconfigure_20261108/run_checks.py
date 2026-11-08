"""Compose current receive-ready, NI configuration, and live data protocols.

Uses artificial fixtures only. Fixed configurations are not an optimization
algorithm, and fixture Gate times are not application profiling results.
"""
from pathlib import Path
from collections import Counter
import argparse,csv,datetime,hashlib,json,os,subprocess
R=Path(__file__).resolve().parent
TARGET=Path('/mnt/sda1/h4567/qwen15_moe_target_v36_20261009')
ap=argparse.ArgumentParser();ap.add_argument('--attempt',default='');ap.add_argument('--probe-fixed',action='store_true');args=ap.parse_args()
assert not args.attempt or args.attempt.isalnum()
suffix='_'+args.attempt if args.attempt else ''
OUT=R/('runs'+suffix);OUT.mkdir(exist_ok=False)
state={'state':'running','scope':'joint ready/configuration protocol fixtures, not application performance','cases':[]}
def save():
    state['updated']=datetime.datetime.now().isoformat()
    p=R/('status'+suffix+'.tmp');p.write_text(json.dumps(state,indent=2));p.replace(R/('status'+suffix+'.json'))
def run(name,fixture,gate=False):
    case=OUT/name;case.mkdir()
    source=R/'inputs'
    cfg=(source/(fixture+'.cfg')).read_text()
    plan=(source/(fixture+'.plan')).read_text().splitlines()
    old=[]
    for line in (source/(fixture+'.trace')).read_text().splitlines():
        if line.strip():
            v=line.split();old.append([float(v[0])]+list(map(int,v[1:])))
    assert len(old)==48
    if gate:
        # The first 16 routed packets belong to the old configuration. A
        # single-epoch Gate fixture must use only the new configuration's
        # 16 routed packets plus the original middle 16 Mesh packets.
        routes=[]
        for v in cfg.splitlines():
            if v.startswith('route '):
                f=v.split()
                if int(f[1])>=32:
                    f[1]=str(int(f[1])-16);routes.append(' '.join(f)+'\n')
        old=old[16:]
        # Start from all-disabled CS state; release routed data only in epoch 1.
        cfg='params 2 1 1 3 1\n'+''.join('cs %d 0\n'%c for c in range(9))+''.join('node %d 0 0\n'%n for n in range(16))+''.join(routes)
    else:
        # Readiness initialization takes real SRAM edges. Do not freeze before
        # the old-epoch packets have had a chance to acquire their grants.
        plan=[('timing 5000 100000' if v.startswith('timing ') else v) for v in plan]
    bench=[];calendar=[];counts=Counter();demand=[[0]*16 for n in range(16)]
    for p,(t,s,d,flits) in enumerate(old):
        # Tail-credit fixture originally includes header-only packets; use a
        # real 512-byte receive region here so both protocols are exercised.
        flits=max(flits,17)
        size=(flits-1)*32
        ident=0x4e4f800000000000|((p+1)<<24)|(s<<8)|d
        bench.append('%g %g %d %d %d %d\n'%(t,t,s,d,flits,ident))
        calendar.extend(['post %d %d %d %g %d %d\n'%(d,s,ident,t,size,1048576+32768*counts[d]),
                         'descriptor %d %d %d\n'%(d,ident,3900000+32*counts[d])])
        counts[d]+=1;demand[s][d]+=size
    if gate:
        plan=[v for v in plan if not v.startswith(('timing ','packet_epoch ','probe_'))]
        plan+=['timing 0 100000','application_gate_ready 1']
        plan+=['gate %d %d'%(n,100+17*n) for n in range(16)]
        plan+=['demand %d %d %d'%(n,d,demand[n][d]) for n in range(16) for d in range(16)]
        route_ids=[int(v.split()[1]) for v in cfg.splitlines() if v.startswith('route ')]
        plan+=['packet_epoch %d 1'%p for p in route_ids]
    (case/'config.txt').write_text(cfg)
    (case/'plan.txt').write_text('\n'.join(plan)+'\n')
    (case/'bench.txt').write_text(''.join(bench));(case/'calendar.txt').write_text(''.join(calendar))
    env={k:v for k,v in os.environ.items() if not k.startswith('NOC_')}
    env.update(NOC_DATA_WIRE='1',NOC_AUX_CONFIG=str(case/'config.txt'),NOC_DYNAMIC_PLAN=str(case/'plan.txt'),
        NOC_AUX_LOG='events.csv',NOC_SOURCE_CAPACITY_FLITS='1025',NOC_SOURCE_LOG='source.csv',
        NOC_RECEIVE_POSTS=str(case/'calendar.txt'),NOC_RECEIVE_READY='1',NOC_SRAM_POLICY='npu_first',
        NOC_STABLE_EVENT_ORDER='2',NOC_CLOCKED_SOURCE_ADMISSION='1',NOC_QUIESCENT_SKIP='0',
        NOC_EMPTY_SKIP='1',NOC_IDLE_ROUTER_FAST='1')
    binary=R/('noc/build/popnet_cs_ni' if args.probe_fixed else 'popnet_cs_ni')
    argv=[str(binary),'-A','16','-c','1','-V','3','-B','8','-O','8','-F','4','-L','2000',
        '-T','350000','-r','1','-I',str(case/'bench.txt'),'-R','4','-G',str(TARGET/'noc_mesh_4x4_v3_6_candidate.gv'),'-D','delay.txt','-P']
    with (case/'run.log').open('xb') as f:
        cp=subprocess.run(argv,cwd=case,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=180)
    assert cp.returncode==0,(name,cp.returncode,(case/'run.log').read_text()[-2000:])
    bridge=json.loads((case/'bridge_summary.json').read_text())
    dynamic=json.loads((case/'dynamic_summary.json').read_text())
    ready=json.loads((case/'receive_ready_summary.json').read_text())
    wire=json.loads((case/'wire_summary.json').read_text())
    assert dynamic['passed'] and ready['state']=='passed'
    assert ready['notifications']==ready['received']==ready['data_admissions']==len(old)
    assert bridge['completed_packets']==len(old)
    assert bridge['written_flits']==sum(max(v[3],17) for v in old)
    assert bridge['aux_written']==bridge['aux_sent']==bridge['aux_credits_returned']>0
    assert bridge['control_retired_flits']==wire['serialized_control_headers']>len(old)
    with (case/'control_events.csv').open() as f:control=list(csv.DictReader(f))
    assert sum(v['event']=='COMMIT' for v in control)==41
    commits=[float(v['time']) for v in control if v['event']=='COMMIT']
    with (case/'wire_headers.csv').open() as f:headers=list(csv.DictReader(f))
    sources={(v['packet'],v['source'],v['destination']):v['wire_word'] for v in headers if v['event'] in ('SOURCE','SOURCE_CONTROL')}
    for v in headers:assert v['wire_word']==sources[v['packet'],v['source'],v['destination']]
    epochs={int(v['epoch']) for v in headers if v['event']=='SOURCE' and v['aux']=='1'}
    assert epochs==({1} if gate else {0,1})
    with (case/'events.csv').open() as f:events=list(csv.DictReader(f))
    ni=Counter((v['node'],v['time']) for v in events if v['event'].startswith(('WRITE_','HEADER_')))
    assert max(ni.values())==1
    service=Counter()
    for filename,event in [('source.csv','RELEASE'),('receive_events.csv',None)]:
        with (case/filename).open() as f:
            for v in csv.DictReader(f):
                if (v['event']==event if event else int(v['bytes'])>0):service[int(v['node']),int(float(v['time']))]+=1
    assert max(service.values())==1
    if gate:
        phase=json.loads((case/'phase_demand.json').read_text())
        assert phase['received_masks']==[7]*16 and phase['cpu_received_bytes']==demand
        assert all(float(t)>max(commits) for t in phase['resume_times'])
    result={'name':name,'state':'passed','data_packets':len(old),'real_receive_ready_controls':len(old),
        'total_real_control_headers':wire['serialized_control_headers'],'CS_commits':41,
        'source_epochs':sorted(epochs),'AUX_flits':bridge['aux_written'],
        'same_port_and_header_checks_passed':True,'real_Gate_notification_round_trip':gate}
    (case/'validation.json').write_text(json.dumps(result,indent=2))
    state['cases'].append(result);save()
save()
try:
    binary=R/('noc/build/popnet_cs_ni' if args.probe_fixed else 'popnet_cs_ni')
    state['binary_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
    state['test_probe_corrected']=args.probe_fixed
    if not args.probe_fixed:assert state['binary_sha256']=='e6058e940931db3835c4bef6704354aac10851070bc1e0c1f90b65a3f033278a'
    for fixture in ('transition','credit_tail','selector_move'):run(fixture+'_ready',fixture)
    run('Gate_config_receive_ready','transition',gate=True)
    state['state']='passed'
except BaseException as e:
    state.update(state='failed',reason=repr(e));save();raise
finally:save()
