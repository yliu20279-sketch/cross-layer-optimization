"""Validate explicit native DRAM dependencies, never infer them from time."""
from pathlib import Path
from collections import Counter
import csv,json
def prepare(rid,offset=16,expected_services=None,expected_commands=None):
    out=Path('explicit_memory_program.txt').open('w');services=Counter();commands={};dram_count=waits=0
    for n in range(16):
        actor=Path.cwd().parent/f'proc_r{rid}_p1_t{n+offset}'
        with (actor/'reports/dram_transactions.csv').open() as h:dram={int(v['request_id']):v for v in csv.DictReader(h)}
        bases={0:0};current=0
        with (actor/'causal_memory_program.txt').open() as h:
            for line in h:
                v=line.split();assert int(v[1])==n;f=int(v[2]);kind=v[0]
                if kind=='service':
                    assert len(v)==6 and f==current
                    off,b,time=map(int,v[3:]);assert off>0 and time==bases[f]+off
                    services[n,time,b]+=1
                elif kind=='release':
                    assert len(v)==6 and f==current
                    desc,send,off=map(int,v[3:]);key=n,desc,send;assert off>=0 and key not in commands
                    commands[key]=bases[f]+off
                elif kind=='dram':
                    assert len(v)==10 and f==current+1
                    parent,gap,write,address,b,request,after=map(int,v[3:]);assert parent==current and gap>=0
                    d=dram.pop(request);before=bases[parent]+gap
                    assert (d['operation']=='STORE')==bool(write) and int(d['address'])==address and int(d['bytes'])==b
                    assert before==int(d['issue_cycle']) and after==before+int(d['external_elapsed_cycles'])
                    bases[f]=after;current=f;dram_count+=1
                else:
                    assert kind=='fence' and len(v)==8 and f==current+1
                    parent,gap,tx,rx,after=map(int,v[3:]);assert parent==current and gap>=0 and (tx or rx)
                    assert after>=bases[parent]+gap;bases[f]=after;current=f;waits+=1
                out.write(line)
        assert not dram,('missing actual memory calls',n,len(dram))
    out.close()
    if expected_services is not None:assert services==expected_services,'enhanced observer changed/lost actual SRAM services'
    if expected_commands is not None:assert commands==expected_commands,'enhanced observer changed/lost issued commands'
    result={'state':'passed','actual_native_DRAM_requests':dram_count,'actual_SRAM_service_records':sum(services.values()),
            'actual_commands':len(commands),'actual_blocking_NoC_waits':waits,'dependencies_recorded_inside_native_calls':True}
    Path('explicit_memory_program_proof.json').write_text(json.dumps(result,indent=2));return result
