"""Independent actual-resource and DAG audit for posted receives.

Does not require the obsolete single incoming SRAM block or original receive
row order. It does require exact graph coverage, producer dependencies and
non-overlapping lifetimes of the concrete allocated receive intervals.
"""
from pathlib import Path
from collections import Counter,defaultdict
import argparse
import csv
import hashlib
import json
import re

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return list(csv.DictReader(p.open()))
def streamed_rows(p):
    with p.open() as handle:
        yield from csv.DictReader(handle)
def audit(case,require_closed=True):
    work=case/'run';status={'state':'auditing','performance_result':False,'require_closed':require_closed}
    output=case/('physical_application_audit.json' if require_closed else 'warmup_causality_diagnostic.json')
    def save():output.write_text(json.dumps(status,indent=2))
    save()
    try:
        hashes=json.loads((case/'input_hashes.json').read_text());assert all(sha(Path(p))==h for p,h in hashes.items())
        plans=Path(json.loads((case/'plan_pointer.json').read_text())['path'])
        nets=sorted(work.glob('proc_r*_p2_t0'),key=lambda p:int(p.name.split('_')[1][1:]))
        net=nets[-1];rid=int(net.name.split('_')[1][1:]);log=(case/'launcher.log').read_text()
        if require_closed:
            for r in (rid-1,rid):
                solved=work/f'proc_r{r}_p2_t0'
                assert json.loads((solved/'causal_command_audit.json').read_text())['altered_request_timestamps']==0,('numerical request clock still active',r)
                assert sha(solved/'effective_input_bench.txt')==sha(solved/'stable_input_bench.txt'),('request times still different from actual NPU',r)
                guide=json.loads((work/f'proc_r{r}_p2_t0/program_fences_summary.json').read_text())
                assert guide['retimed_services']==guide['release_deferrals']==0,('temporary numerical guidance still active',r,guide)
                assert guide['retimed_DRAM_completions']==0,('native memory waveforms still not fixed',r,guide)
                queries=rows(solved/'dram_program_queries.csv')
                assert len(queries)==guide['actual_native_DRAM_requests']
                assert all(v['actual']==v['nominal'] for v in queries),'native memory completion guidance still active'
                for n in range(16):
                    for prediction in rows(work/f'proc_r{r}_p1_t{n+16}'/'ring_prediction_bounds.csv'):
                        assert int(prediction['applied'])==0,('numerical port bound still active',r,n,prediction)
            assert 'Simulation cycle has converged;' in log and len(nets)>=2
            assert sha(net/'output_delayInfo.txt')==sha(nets[-2]/'output_delayInfo.txt')
            for file in ('source.csv','events.csv','receive_events.csv','receive_ready_events.csv'):
                assert sha(net/file)==sha(nets[-2]/file),('raw network states not fixed',file)
        feedback={}
        for line in (net/'output_delayInfo.txt').read_text().splitlines():
            ts,s,d,desc,num,send,recv=map(int,line.split());assert num==2
            key=s,d,desc;assert key not in feedback;feedback[key]=(ts,ts+send,ts+recv)
        assert json.loads((net/'source_audit.json').read_text())['passed']
        assert json.loads((net/'receive_ready_summary.json').read_text())['state']=='passed'
        expected=rows(plans/'expected_messages.csv')
        assert set(feedback)=={(int(r['source']),int(r['destination']),int(r['descriptor'])) for r in expected}
        sends={};receives={};posted={};vertices={};local_uses=Counter();ni_uses=Counter();commits={};bounds=[]
        times=[]
        for n in range(16):
            actor=work/f'proc_r{rid}_p1_t{n+16}';plan=json.loads((plans/f'node_{n}.json').read_text())
            actual=rows(actor/'vertices.csv');owned=[r for r in actual if r['kind']!='transfer_send']
            assert Counter(int(r['op']) for r in owned)==Counter(o['id'] for o in plan['operators'] if o['rank']==n)
            for r in owned:
                op=int(r['op']);start=int(r['start']);finish=int(r['finish']);assert finish>=start
                assert op not in commits;commits[op]=finish;vertices[n,op]=(start,finish)
            for r in rows(actor/'posted_descriptors.csv'):
                desc=int(r['descriptor']);assert (n,desc) not in posted;posted[n,desc]=r
                a=int(r['buffer']);b=int(r['bytes']);m=int(r['metadata_address'])
                assert a>=int(r['local_workspace_limit']) and a+b<=4063232 and m+32<=4063232
            for r in rows(actor/'communication.csv'):
                peer=int(r['peer']);desc=int(r['descriptor']);send=r['role']=='send'
                s,d=(n,peer) if send else (peer,n);key=s,d,desc
                target=sends if send else receives;assert key not in target;target[key]=r
                ts,sd,rd=feedback[key];issue=int(r['issue']);done=int(r['done'])
                assert done>=issue
                if send:
                    assert issue==ts and done>=sd
                    if require_closed:assert done==sd,('cached source completion not actual fixed point',key,done,sd)
                else:
                    assert done>=rd
                    if require_closed:assert done==rd,('cached receive completion not actual fixed point',key,done,rd)
                    p=posted[n,desc];assert int(p['post_cycle'])==issue and int(p['buffer'])==int(r['buffer'])
            for file in ('sram_service','kernel_sram_service','exchange_sram_service','packing_sram_service'):
                path=actor/(file+'.csv')
                if not path.exists():continue
                for r in rows(path):
                    assert int(r.get('node',n))==n
                    t=int(r['time']);byte=int(r['bytes']);assert 0<byte<=256
                    assert int(r['address'])+byte<=4063232
                    local_uses[n,t]+=1
            dram=rows(actor/'reports/dram_transactions.csv')
            assert dram and all(int(r['issue_cycle'])>=0 and int(r['external_elapsed_cycles'])>0 for r in dram)
            times.append({'node':n,'vertices':len(owned),'finish_cycle':max(int(r['finish']) for r in owned),'DRAM_completions':len(dram)})
        assert set(sends)==set(receives)==set(feedback)
        first={};last={};source_key={(s,v[0]):(s,d,desc) for (s,d,desc),v in feedback.items()}
        assert len(source_key)==len(feedback)
        for r in streamed_rows(net/'source.csv'):
            if r['event']=='RELEASE':ni_uses[int(r['node']),int(float(r['time']))]+=1
        for r in streamed_rows(net/'receive_events.csv'):
            n=int(r['node']);t=int(float(r['time']));byte=int(r['bytes'])
            if byte:ni_uses[n,t]+=1
            if r['event']=='WRITE':
                desc=int(r['message_id']);key=int(r['source']),n,desc
                assert key in receives
                first.setdefault(key,t);last[key]=t
                receive=receives[key];a=int(receive['buffer']);b=int(receive['bytes'])
                assert a<=int(r['address']) and int(r['address'])+byte<=a+b
        assert set(first)==set(feedback)
        combined=local_uses+ni_uses
        conflicts=[(n,t,v) for (n,t),v in combined.items() if v>1]
        assert not conflicts,('single SRAM port conflict',conflicts[:8])
        for n in range(16):
            previous=0
            for key,r in sorted(((k,v) for k,v in sends.items() if k[0]==n),key=lambda kv:int(kv[1]['prepare'])):
                assert int(r['prepare'])>=previous,'source staging reused before actual source release'
                previous=feedback[key][1]
            # Only concrete overlapping address ranges require serialization;
            # independent preposted buffers may receive concurrently.
            lifetimes=[]
            for key,r in receives.items():
                if key[1]!=n:continue
                a=int(r['buffer']);b=int(r['bytes']);finish=int(r['consume_finish'])
                assert first[key]>=int(r['issue']) and last[key]<=int(r['done'])<=finish
                lifetimes.append((a,a+b,first[key],finish,key))
            for i,(a,b,start,finish,key) in enumerate(lifetimes):
                for c,d,other_start,other_finish,other in lifetimes[i+1:]:
                    assert b<=c or d<=a or finish<=other_start or other_finish<=start,('receive buffer lifetime overlap',key,other)
        graph=json.loads((plans/'node_0.json').read_text())['operators'];by_id={o['id']:o for o in graph};producer={}
        for op in graph:
            for name in [op['output']]+op.get('secondary_outputs',[]):producer[name]=op['id']
        for (n,op),(start,finish) in vertices.items():
            for name in by_id[op]['inputs']:
                p=producer.get(name)
                if p is not None and by_id[p]['rank']==n:
                    assert start>=commits[p],('local consumer before producer',n,op,p)
        for key,r in sends.items():
            n=key[0];op=int(r['op'])
            for name in by_id[op]['inputs']:
                p=producer.get(name)
                if p is not None and by_id[p]['rank']==n:
                    assert int(r['prepare'])>=commits[p],('remote send before local producer',key,p)
        status.update(state='passed',strict_rounds=len(nets),messages=len(feedback),actual_graph_vertex_times=times,
            zero_SRAM_port_conflicts=True,zero_receive_buffer_lifetime_conflicts=True,all_vertices_and_messages_present=True,
            zero_local_DAG_dependency_violations=True,final_feedback_sha256=sha(net/'output_delayInfo.txt'),
            performance_result=False,scope='selected validated decoder blocks; not a complete HiBand/proposed comparison',
            decoder_blocks=json.loads((plans/'node_0.json').read_text())['layer_limit'])
    except BaseException as e:status.update(state='failed',reason=str(e));raise
    finally:save()
    return status

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('case',type=Path);ap.add_argument('--diagnostic-only',action='store_true')
    args=ap.parse_args();print(json.dumps(audit(args.case,not args.diagnostic_only),indent=2))
