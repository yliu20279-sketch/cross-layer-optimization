"""Short native chain acceptance: physical, causal, and independent references."""
from pathlib import Path
from collections import Counter
import csv,datetime,hashlib,importlib.util,json,os,shutil,subprocess
R=Path(__file__).resolve().parent;B=R.parent
TARGET=Path('/mnt/sda1/h4567/qwen15_moe_target_v36_20261009')
def rows(p):
    with p.open() as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
memory_audit=load(R/'audit_memory_queries.py','short_memory_oracle')
hb=load(B/'noc_hb_transport_20261108/audit_hb.py','short_independent_hb')
q={ '__file__':str(R/'reference_functions.py') }
source=B/'noc_clocked_causal_20261108/pipeline.py'
exec(compile(source.read_text().split('\nsave()\ntry:')[0],str(source),'exec'),q)
state={'state':'auditing','scope':'short native vector/DMA/DDR and NI configuration integration',
       'application_performance_claim':False,'cases':{}}
def save():state['updated']=datetime.datetime.now().isoformat();(R/'chain_acceptance_retry1.json').write_text(json.dumps(state,indent=2))
save()
try:
    last_cases={}
    for mode in ('absolute','relative'):
        case=R/mode;work=case/'run'
        result=json.loads((case/'result.json').read_text());assert result['exit']==0 and result['converged']
        nets=sorted(work.glob('proc_r*_p2_t0'),key=lambda p:int(p.name.split('_')[1][1:]));rid=int(nets[-1].name.split('_')[1][1:])
        assert len(nets)>=2
        evidence=case/'evidence_retry1';evidence.mkdir()
        for step in (rid-1,rid):memory_audit.audit(work,step,evidence/f'oracle_round{step}.json',offset=0)
        hb.audit(work,rid,0,evidence/'independent_native_DRAM.json')
        net=nets[-1];last_cases[mode]=net
        b=json.loads((net/'bridge_summary.json').read_text());d=json.loads((net/'dynamic_summary.json').read_text())
        ready=json.loads((net/'receive_ready_summary.json').read_text());phase=json.loads((net/'phase_demand.json').read_text())
        assert b['completed_packets']==48 and b['written_flits']==3120
        assert b['aux_sent']==b['aux_written']==b['aux_credits_returned']==1040 and b['mesh_written']==2080
        assert d['passed'] and d['phase_notifications']==48
        assert ready['notifications']==ready['received']==ready['data_admissions']==48
        control=rows(net/'control_events.csv');commits=[float(v['time']) for v in control if v['event']=='COMMIT']
        assert len(commits)==41
        cpu=[float(v['time']) for v in control if v['event']=='CPU_DEMAND_RECEIVED']
        loads=[float(v['time']) for v in control if v['event']=='LOAD']
        assert len(cpu)==48 and min(loads)>=max(cpu)
        assert all(float(t)>max(commits) for t in phase['resume_times'])
        feedback={}
        for line in (net/'output_delayInfo.txt').read_text().splitlines():
            ts,s,dt,desc,num,sd,rd=map(int,line.split());assert num==2
            feedback[desc]=(ts,ts+sd,ts+rd,s,dt)
        assert len(feedback)==48
        local=Counter();ni=Counter();vector_ops=0
        for n in range(16):
            actor=work/f'proc_r{rid}_p1_t{n}'
            events=rows(actor/'local_events.csv');g=rows(actor/'gate_events.csv')
            assert len(g)==1 and int(g[0]['configuration_ready_cycle'])==phase['gate_times'][n]
            prior=max(int(v['finish']) for v in events if v['label']=='rs_reduce_s0')
            assert int(g[0]['configuration_ready_cycle'])==prior
            for v in rows(actor/'communication.csv'):
                desc=int(v['descriptor']);step=((desc>>20)&15)-1
                t,sd,rd,s,dt=feedback[desc]
                if v['role']=='send':assert int(v['issue'])==t and int(v['done'])==sd and s==n
                else:
                    assert int(v['issue'])<=rd and int(v['done'])==rd and dt==n
                    posted=[p for p in rows(actor/'posted_descriptors.csv') if int(p['descriptor'])==desc]
                    assert len(posted)==1 and int(posted[0]['post_cycle'])==int(v['issue'])
                    consumer=[x for x in events if x['label']=='rs_reduce_s%d'%step]
                    assert consumer and min(int(x['issue']) for x in consumer)>=rd
                    assert max(int(x['finish']) for x in consumer)==int(v['consume_finish'])
            for v in rows(actor/'join_bounds.csv'):
                assert int(v['applied'])==0
                assert int(v['join'])==max(int(v['source']),int(v['receive']))
            for v in events:
                if v['kind']=='vector_add':vector_ops+=int(v['ops'])
            for file in ('sram_service.csv','exchange_sram_service.csv'):
                for v in rows(actor/file):
                    assert int(v['address'])+int(v['bytes'])<=4063232
                    local[n,int(v['time'])]+=1
            posts=rows(actor/'posted_descriptors.csv');receives=[v for v in rows(actor/'communication.csv') if v['role']=='receive']
            assert len(posts)==len(receives)==3
            for old,new in zip(receives,receives[1:]):assert int(new['issue'])>=int(old['consume_finish'])
        assert vector_ops==16*3*1024
        for v in rows(net/'source.csv'):
            if v['event']=='RELEASE':ni[int(v['node']),int(float(v['time']))]+=1
        for v in rows(net/'receive_events.csv'):
            if int(v['bytes']):ni[int(v['node']),int(float(v['time']))]+=1
        assert max((local+ni).values())==1
        headers=rows(net/'wire_headers.csv');original={}
        for v in headers:
            key=v['packet'],v['source'],v['destination']
            if v['event'] in ('SOURCE','SOURCE_CONTROL'):assert key not in original;original[key]=v['wire_word']
            else:assert v['wire_word']==original[key]
            if v['event']=='SOURCE' and v['aux']=='1':
                assert int(v['epoch'])==1 and float(v['time'])>=phase['resume_times'][int(v['source'])]
        ref=evidence/'independent_NoC';ref.mkdir()
        for name in ('stable_input_bench.txt','receive_calendar.txt','active_topology.cfg','dynamic.plan'):shutil.copy2(net/name,ref/name)
        env={k:v for k,v in os.environ.items() if not k.startswith('NOC_')}
        env.update(NOC_DATA_WIRE='1',NOC_AUX_CONFIG=str(ref/'active_topology.cfg'),NOC_DYNAMIC_PLAN=str(ref/'dynamic.plan'),
            NOC_AUX_LOG='events.csv',NOC_SOURCE_CAPACITY_FLITS='1025',NOC_SOURCE_LOG='source.csv',
            NOC_RECEIVE_POSTS=str(ref/'receive_calendar.txt'),NOC_SRAM_POLICY='npu_first',NOC_RECEIVE_READY='1',
            NOC_ROUTER_STALL_LOG='router_stalls',NOC_QUIESCENT_SKIP='0',NOC_STABLE_EVENT_ORDER='2',NOC_CLOCKED_SOURCE_ADMISSION='1')
        end=max(v[2] for v in feedback.values())+10000
        args=[str(R/'reference_noc/build/popnet_cs_ni'),'-A','16','-c','1','-V','3','-B','8','-O','8','-F','4','-L','2000',
              '-T',str(end),'-r','1','-I','stable_input_bench.txt','-R','4','-G',str(TARGET/'noc_mesh_4x4_v3_6_candidate.gv'),'-D','delayInfo.txt','-P']
        with (ref/'run.log').open('xb') as f:subprocess.run(args,cwd=ref,env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
        proof=q['equivalent'](net,ref)
        assert sha(net/'control_events.csv')==sha(ref/'control_events.csv')
        (evidence/'independent_NoC_validation.json').write_text(json.dumps(proof,indent=2))
        state['cases'][mode]={'state':'passed','strict_rounds':rid,'native_vector_ops':vector_ops,
            'actual_native_DRAM_transactions':64,'application_messages':48,'actual_AUX_flits':1040,
            'all_shared_port_and_consumer_dependencies_checked':True,'independent_NoC_and_DRAM_passed':True};save()
    cross=q['equivalent'](last_cases['absolute'],last_cases['relative'])
    (R/'predictor_mode_independence_retry1.json').write_text(json.dumps(cross,indent=2))
    assert all(sha(Path(p))==h for p,h in json.loads((R/'chain_input_hashes.json').read_text()).items())
    state.update(state='passed',predictor_modes_same_physical_result=True,
                 original_simulation_input_hashes_unchanged=True,
                 scope='short real native chain plus actual NI configuration protocol; not complete Qwen or performance evaluation')
except BaseException as e:state.update(state='failed',reason=repr(e));save();raise
finally:save()
