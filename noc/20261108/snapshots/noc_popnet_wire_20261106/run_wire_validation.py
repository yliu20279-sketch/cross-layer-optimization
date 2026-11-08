"""Native, serialized-header/VC-context engineering tests; no performance claim."""
from pathlib import Path
import collections
import csv
import hashlib
import json
import os
import platform
import subprocess
import traceback

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'wire_build'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=False)
    report = {'status': 'running', 'host': platform.node(), 'application_performance': False,
              'cases': {}, 'commands': []}
    def save():
        (OUT / 'validation.json').write_text(json.dumps(report, indent=2))
    def run(name, cfg, trace, plan=None, wire=True, fault=None, expect=0, sync=False):
        d = OUT / name
        d.mkdir()
        env = dict(os.environ)
        for key in ('NOC_AUX_CONFIG','NOC_AUX_LOG','NOC_DYNAMIC_PLAN','NOC_DATA_WIRE','NOC_WIRE_FAULT'):
            env.pop(key,None)
        env.update(NOC_AUX_CONFIG=str(cfg),NOC_AUX_LOG=str(d/'events.csv'))
        if wire: env['NOC_DATA_WIRE']='1'
        if plan: env['NOC_DYNAMIC_PLAN']=str(plan)
        if fault: env['NOC_WIRE_FAULT']=fault
        args = [str(ROOT/'build/cmake/popnet_cs_ni'),'-A','16','-c','1','-V','3','-B','8',
                '-O','8','-F','4','-R','4','-G',str(ROOT/'inputs/target_mesh.gv'),
                '-T','160000','-r','1','-I',str(trace),'-D',str(d/'delay.txt')]
        if sync: args.append('-P')
        result = subprocess.run(args,cwd=d,env=env,capture_output=True,text=True,timeout=180)
        log = d/'popnet.stdout.log'
        log.write_text(result.stdout+result.stderr)
        report['commands'].append({'case':name,'argv':args,'returncode':result.returncode,
                                   'expected':expect,'log_sha256':sha(log)})
        save()
        assert result.returncode==expect,(name,result.stderr[-1200:])
        return d
    def inspect(d):
        s=json.loads((d/'wire_summary.json').read_text())
        b=json.loads((d/'bridge_summary.json').read_text())
        rows=list(csv.DictReader((d/'wire_headers.csv').open()))
        sources={(r['packet'],r['source'],r['destination']):r for r in rows
                 if r['event'] in ('SOURCE','SOURCE_CONTROL')}
        for row in rows:
            if row['event'] in ('SOURCE','SOURCE_CONTROL'):continue
            assert row['wire_word']==sources[(row['packet'],row['source'],row['destination'])]['wire_word'],row
            if row['event']=='AUX_TX_HEADER':assert row['node']==row['gateway']
            if row['event']=='AUX_RX_HEADER':assert row['node']==row['destination']
        assert len([r for r in rows if r['event']=='SOURCE'])==s['serialized_data_headers']
        assert len([r for r in rows if r['event']=='SOURCE_CONTROL'])==s['serialized_control_headers']
        assert not s['router_uses_packet_table']
        assert s['serialized_data_headers']+s['unchanged_body_flits']==b['written_flits']
        assert b['data_header_retired_flits']==s['serialized_data_headers']
        assert b['payload_written_flits']==s['unchanged_body_flits']
        assert s['serialized_control_headers']==b['control_retired_flits']
        events=list(csv.DictReader((d/'events.csv').open()))
        writes=collections.Counter((r['time'],r['node']) for r in events
                                   if r['event'].startswith(('WRITE_','HEADER_')))
        assert max(writes.values())==1
        assert all(r['node']==r['destination'] for r in events if r['event']=='COMPLETE')
        report['cases'][d.name]={'wire':s,'bridge':b,'header_words_preserved':True}
        return rows
    save()
    try:
        assert (ROOT/'legacy.exit').read_text().strip()=='0'
        # Here the first flit is explicitly reserved as a header, including
        # header-only SINGLE fixtures. Body flits remain full 256-bit data.
        plain=ROOT/'inputs/plain_wire.cfg'
        plain.write_text('params 2 1 1 3 1\n'+''.join(f'cs {c} 0\n' for c in range(9))+
                         ''.join(f'node {n} 0 0\n' for n in range(16)))
        legacy=run('plain_legacy',plain,ROOT/'inputs/baseline.trace',wire=False)
        d=run('plain_wire',plain,ROOT/'inputs/baseline.trace')
        inspect(d)
        assert (legacy/'delay.txt').read_bytes()==(d/'delay.txt').read_bytes()
        for name in ('mixed','sync'):
            d=run(name+'_wire',ROOT/'inputs'/f'{name}.cfg',ROOT/'inputs'/f'{name}.trace',sync=name=='sync')
            inspect(d)
            assert (d/'delay.txt').read_bytes()==(ROOT/'build'/('static_'+name)/'delay.txt').read_bytes()
        for c in range(9):
            raw=run(f'cs{c}_legacy',ROOT/'inputs'/f'cs{c}.cfg',ROOT/'inputs'/f'cs{c}.trace',wire=False)
            d=run(f'cs{c}_wire',ROOT/'inputs'/f'cs{c}.cfg',ROOT/'inputs'/f'cs{c}.trace')
            inspect(d)
            assert (raw/'delay.txt').read_bytes()==(d/'delay.txt').read_bytes()
        for name in ('transition','credit_tail','selector_move','timeout','credit_timeout'):
            negative=name in ('timeout','credit_timeout')
            d=run(name+'_wire',ROOT/'inputs'/f'{name}.cfg',ROOT/'inputs'/f'{name}.trace',
                  plan=ROOT/'inputs'/f'{name}.plan',expect=1 if negative else 0)
            s=json.loads((d/'dynamic_summary.json').read_text())
            ctrl=list(csv.DictReader((d/'control_events.csv').open()))
            if negative:
                assert not s['passed'] and s['frozen_nodes']==16
                assert not any(r['event'] in ('COMMIT','RUN') for r in ctrl)
                report['cases'][d.name]={'fail_closed':True,'controller':s}
            else:
                rows=inspect(d)
                assert s['passed'] and s['duplicate_arm_preserved'] and s['ignored_responses']>=1
                assert len([r for r in ctrl if r['event']=='COMMIT'])==41
                assert {int(r['epoch']) for r in rows if r['event']=='SOURCE' and r['aux']=='1'}=={0,1}
                assert (d/'delay.txt').read_bytes()==(ROOT/'build'/name/'delay.txt').read_bytes()
                report['cases'][d.name]['controller']=s
        # Corrupt the actual head after the first physical Mesh output, not the
        # source descriptor or a scoreboarding copy. Every case must fail.
        base=(ROOT/'inputs/mixed.cfg').read_text().splitlines()
        cfg=ROOT/'inputs/fault_wire.cfg'
        cfg.write_text('\n'.join(x for x in base if not x.startswith('route '))+'\nroute 0 15 5 0\n')
        trace=ROOT/'inputs/fault_wire.trace';trace.write_text('1 15 5 17\n')
        reasons={'type':'not a data header','padding':'nonzero data-header padding',
                 'source':'serialized source/final destination mismatch',
                 'gateway':'AUX output context/physical connection mismatch',
                 'epoch':'CS header epoch differs from destination NI active epoch'}
        for fault,reason in reasons.items():
            d=run('fault_'+fault,cfg,trace,fault=fault,expect=1)
            assert reason in (d/'popnet.stdout.log').read_text(),(fault,reason)
            rows=list(csv.DictReader((d/'wire_headers.csv').open()))
            assert len([r for r in rows if r['event']=='FAULT'])==1
            events=list(csv.DictReader((d/'events.csv').open()))
            assert not any(r['event']=='COMPLETE' for r in events)
            report['cases'][d.name]={'actual_link_fault_rejected':True,'reason':reason}
        report['status']='passed_serialized_header_native_popnet'
        report['sha256']={p.relative_to(ROOT).as_posix():sha(p) for folder in ('adapter','inputs')
                          for p in sorted((ROOT/folder).rglob('*')) if p.is_file()}
        for name in ('run_wire_validation.py','run_validation.py','main_bridge.cc','CMakeLists.txt'):
            report['sha256'][name]=sha(ROOT/name)
        report['sha256']['build/cmake/popnet_cs_ni']=sha(ROOT/'build/cmake/popnet_cs_ni')
        for p in sorted(OUT.rglob('*')):
            if p.is_file() and p.name!='validation.json':report['sha256'][p.relative_to(ROOT).as_posix()]=sha(p)
        save();print(json.dumps({'status':report['status'],'cases':len(report['cases'])},indent=2))
    except BaseException as exc:
        report['status']='failed';report['error']=str(exc);save();traceback.print_exc();raise


if __name__=='__main__':main()
