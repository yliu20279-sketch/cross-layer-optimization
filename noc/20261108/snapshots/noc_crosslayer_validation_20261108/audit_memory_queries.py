from pathlib import Path
import csv,json
def read(path):
    with path.open() as h:return list(csv.DictReader(h))
def audit(work,rid,output,offset=16):
    q={};path=work/f'proc_r{rid}_p2_t0/dram_program_queries.csv'
    for v in read(path):
        key=int(v['node']),int(v['request_id']);assert key not in q;q[key]=v
    total=0
    for n in range(16):
        actor=work/f'proc_r{rid}_p1_t{n+offset}'
        server={int(v['request_id']):v for v in read(work/f'reports/ramulator2_ch{n}.csv')}
        for c in read(actor/'reports/dram_transactions.csv'):
            request=int(c['request_id']);v=q.pop((n,request));s=server.pop(request)
            assert (v['write']=='1')==(c['operation']=='STORE')
            assert (int(v['address']),int(v['bytes']),int(v['issue']))==(int(c['address']),int(c['bytes']),int(c['issue_cycle']))
            assert int(v['actual'])==int(v['nominal'])==int(c['issue_cycle'])+int(c['external_elapsed_cycles'])
            assert [int(v[k]) for k in ('arrival','service_start_tick','service_end_tick','service_done','actual')]==[
                int(s[k]) for k in ('service_start_cycle','dram_service_start_tick','dram_service_end_tick','service_done_cycle','response_issue_cycle')]
            total+=1
        assert not server
    assert not q
    proof={'state':'passed','round':rid,'requests':total,'all_oracle_issue_and_completion_times_equal_actual_native':True,
           'all_oracle_memory_ticks_equal_actual_server':True,'numerical_guidance_effect_zero':True,'performance_claim':False}
    output.write_text(json.dumps(proof,indent=2));return proof
