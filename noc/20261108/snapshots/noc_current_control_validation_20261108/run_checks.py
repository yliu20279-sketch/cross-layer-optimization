"""Current clocked/finite-source NI configuration protocol regression."""
from pathlib import Path
from collections import Counter
import argparse,csv,datetime,hashlib,json,os,subprocess
R=Path(__file__).resolve().parent;B=R.parent;TARGET=Path('/mnt/sda1/h4567/qwen15_moe_target_v36_20261009')
ap=argparse.ArgumentParser();ap.add_argument('--attempt',default='');args=ap.parse_args()
assert not args.attempt or args.attempt.isalnum();suffix='_'+args.attempt if args.attempt else ''
OUT=R/('runs'+suffix);OUT.mkdir(exist_ok=False)
state={'state':'running','scope':'component protocol only; not an application/HiBand performance run','cases':[]}
def save():state['updated']=datetime.datetime.now().isoformat();(R/('status'+suffix+'.json')).write_text(json.dumps(state,indent=2))
def run(name,cfg,trace,plan=None,fault=None,expect=0,sync=False):
    case=OUT/name;case.mkdir()
    env={k:v for k,v in os.environ.items() if not k.startswith('NOC_')}
    env.update(NOC_DATA_WIRE='1',NOC_AUX_CONFIG=str(cfg),NOC_AUX_LOG='events.csv',NOC_SOURCE_CAPACITY_FLITS='1025',NOC_SOURCE_LOG='source.csv',
               NOC_STABLE_EVENT_ORDER='2',NOC_CLOCKED_SOURCE_ADMISSION='1',NOC_EMPTY_SKIP='1',NOC_IDLE_ROUTER_FAST='1')
    if plan:env['NOC_DYNAMIC_PLAN']=str(plan)
    if fault:env['NOC_WIRE_FAULT']=fault
    args=[str(R/'popnet_cs_ni'),'-A','16','-c','1','-V','3','-B','8','-O','8','-F','4','-R','4','-L','2000',
          '-G',str(TARGET/'noc_mesh_4x4_v3_6_candidate.gv'),'-T','160000','-r','1','-I',str(trace),'-D','delay.txt']
    if sync:args.append('-P')
    with (case/'run.log').open('xb') as h:cp=subprocess.run(args,cwd=case,env=env,stdout=h,stderr=subprocess.STDOUT,timeout=180)
    assert cp.returncode==expect,(name,cp.returncode,(case/'run.log').read_text()[-1400:])
    return case
def inspect(case):
    w=json.loads((case/'wire_summary.json').read_text());b=json.loads((case/'bridge_summary.json').read_text())
    with (case/'wire_headers.csv').open() as h:rows=list(csv.DictReader(h))
    sources={(v['packet'],v['source'],v['destination']):v for v in rows if v['event'] in ('SOURCE','SOURCE_CONTROL')}
    for v in rows:
        if v['event'] not in ('SOURCE','SOURCE_CONTROL'):assert v['wire_word']==sources[v['packet'],v['source'],v['destination']]['wire_word']
        if v['event']=='AUX_TX_HEADER':assert v['node']==v['gateway']
        if v['event']=='AUX_RX_HEADER':assert v['node']==v['destination']
    assert not w['router_uses_packet_table']
    assert w['serialized_data_headers']+w['unchanged_body_flits']==b['written_flits']
    assert b['data_header_retired_flits']==w['serialized_data_headers'] and b['payload_written_flits']==w['unchanged_body_flits']
    assert w['serialized_control_headers']==b['control_retired_flits']
    assert b['aux_written']==b['aux_sent']==b['aux_credits_returned']
    with (case/'events.csv').open() as h:events=list(csv.DictReader(h))
    writes=Counter((v['time'],v['node']) for v in events if v['event'].startswith(('WRITE_','HEADER_')))
    assert writes and max(writes.values())==1
    state['cases'].append({'name':case.name,'state':'passed','header_words_preserved':True,'CS_credit_conservation':True,
                           'physical_single_NI_write_service_per_cycle':True,'control_headers':w['serialized_control_headers']});save()
    return rows
save()
try:
    inputs=R/'inputs';plain=inputs/'plain_current.cfg'
    plain.write_text('params 2 1 1 3 1\n'+''.join(f'cs {c} 0\n' for c in range(9))+''.join(f'node {n} 0 0\n' for n in range(16)))
    inspect(run('plain',plain,inputs/'baseline.trace'))
    for name in ('mixed','sync'):inspect(run(name,inputs/f'{name}.cfg',inputs/f'{name}.trace',sync=name=='sync'))
    for c in range(9):inspect(run(f'cs{c}',inputs/f'cs{c}.cfg',inputs/f'cs{c}.trace'))
    for name in ('transition','credit_tail','selector_move','timeout','credit_timeout'):
        negative=name in ('timeout','credit_timeout')
        case=run(name,inputs/f'{name}.cfg',inputs/f'{name}.trace',plan=inputs/f'{name}.plan',expect=1 if negative else 0)
        s=json.loads((case/'dynamic_summary.json').read_text())
        with (case/'control_events.csv').open() as h:control=list(csv.DictReader(h))
        if negative:
            assert not s['passed'] and s['frozen_nodes']==16 and not any(v['event'] in ('COMMIT','RUN') for v in control)
            state['cases'].append({'name':name,'state':'expected_fail_closed','no_commit_or_run':True});save()
        else:
            rows=inspect(case)
            assert s['passed'] and s['duplicate_arm_preserved'] and s['ignored_responses']>=1
            assert sum(v['event']=='COMMIT' for v in control)==41
            assert {int(v['epoch']) for v in rows if v['event']=='SOURCE' and v['aux']=='1'}=={0,1}
    cfg=inputs/'fault_current.cfg';cfg.write_text('\n'.join(v for v in (inputs/'mixed.cfg').read_text().splitlines() if not v.startswith('route '))+'\nroute 0 15 5 0\n')
    trace=inputs/'fault_current.trace';trace.write_text('1 15 5 17\n')
    reasons={'type':'not a data header','padding':'nonzero data-header padding','source':'serialized source/final destination mismatch',
             'gateway':'AUX output context/physical connection mismatch','epoch':'CS header epoch differs from destination NI active epoch'}
    for fault,reason in reasons.items():
        case=run('fault_'+fault,cfg,trace,fault=fault,expect=1)
        assert reason in (case/'run.log').read_text()
        with (case/'events.csv').open() as h:assert not any(v['event']=='COMPLETE' for v in csv.DictReader(h))
        state['cases'].append({'name':'fault_'+fault,'state':'actual_header_corruption_rejected','reason':reason});save()
    assert len(state['cases'])==22
    state.update(state='passed',binary_sha256=hashlib.sha256((R/'popnet_cs_ni').read_bytes()).hexdigest(),
                 current_clocked_source_and_same_cycle_order=True,source_capacity_flits=1025)
except BaseException as e:state.update(state='failed',reason=repr(e));save();raise
finally:save()
