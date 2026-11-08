"""Serialized CA tensor transfers completed by the accepted target NoC.

The NoC simulates flits/headers/credits, not arbitrary tensor arithmetic. Actual
tensor bytes remain staged until measured completion, then enter actual HB.
Only one transfer may be outstanding in this first integration version.
"""
from pathlib import Path
import csv
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import types

def load_ca_api(ca_root):
    root=Path(ca_root).resolve()
    package=types.ModuleType('ca_integration_source');package.__path__=[str(root/'core')]
    sys.modules[package.__name__]=package
    name=package.__name__+'.coupled_backend'
    spec=importlib.util.spec_from_file_location(name,root/'core/coupled_backend.py')
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    text=(root/'core/coupled_backend.py').read_text()
    for old,new in [
        ("controls='project_dynamic',timeout=600", "controls='off',timeout=600,npu_config=None"),
        ('str(ram_config),controls]', 'str(ram_config),controls,str(npu_config)]'),
        ('0<op<=13','0<op<=16')]:
        assert text.count(old)==1,old
        text=text.replace(old,new)
    exec(compile(text,str(root/'core/coupled_backend.py'),'exec'),module.__dict__)
    return module

class TargetNoC:
    def __init__(self,binary,expected_sha256,graph,out):
        self.binary=Path(binary).resolve();self.graph=Path(graph).resolve();self.out=Path(out).resolve()
        assert hashlib.sha256(self.binary.read_bytes()).hexdigest()==expected_sha256
        assert not self.out.exists();self.out.mkdir(parents=True)
        self.sequence=0;self.drained_until=0;self.events=[]

    def transfer(self,src,dst,size,issue,mode='mesh'):
        assert 0<=src<16 and 0<=dst<16 and src!=dst and 0<size<=32768 and size%32==0
        assert isinstance(issue,int) and issue>=self.drained_until and mode in ('mesh','static_cs')
        assert mode=='mesh' or (src,dst)==(0,5), 'static probe route is explicitly CS0 NW->SE'
        case=self.out/('transfer_%04d'%self.sequence);case.mkdir()
        descriptor=0x4e4f800000000000|((self.sequence+1)<<24)|(src<<8)|dst
        flits=1+size//32
        cfg='params 2 1 1 3 1\n'
        cfg+=''.join('cs %d %d\n'%(c,2048 if mode=='static_cs' and c==0 else 0) for c in range(9))
        cfg+=''.join('node %d %d %d\n'%(n,16 if mode=='static_cs' and n==0 else 0,
                                            16 if mode=='static_cs' and n==5 else 0) for n in range(16))
        if mode=='static_cs':cfg+='route 0 0 5 0\n'
        (case/'config.txt').write_text(cfg)
        (case/'bench.txt').write_text('%d %d %d %d %d %d\n'%(issue,issue,src,dst,flits,descriptor))
        (case/'calendar.txt').write_text('post %d %d %d %d %d 1048576\ndescriptor %d %d 3900000\n'%
                                        (dst,src,descriptor,issue,size,dst,descriptor))
        env={k:v for k,v in os.environ.items() if not k.startswith('NOC_')}
        env.update(NOC_DATA_WIRE='1',NOC_AUX_CONFIG=str(case/'config.txt'),NOC_AUX_LOG='events.csv',
                   NOC_SOURCE_CAPACITY_FLITS='1025',NOC_SOURCE_LOG='source.csv',
                   NOC_RECEIVE_POSTS=str(case/'calendar.txt'),NOC_RECEIVE_READY='1',NOC_SRAM_POLICY='npu_first',
                   NOC_STABLE_EVENT_ORDER='2',NOC_CLOCKED_SOURCE_ADMISSION='1',NOC_QUIESCENT_SKIP='0',
                   NOC_EMPTY_SKIP='1',NOC_IDLE_ROUTER_FAST='1')
        argv=[str(self.binary),'-A','16','-c','1','-V','3','-B','8','-O','8','-F','4',
              '-L','2000','-T',str(issue+100000),'-r','1','-I',str(case/'bench.txt'),
              '-R','4','-G',str(self.graph),'-D','delay.txt','-P']
        with (case/'run.log').open('xb') as f:
            subprocess.run(argv,cwd=case,env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
        bridge=json.loads((case/'bridge_summary.json').read_text())
        ready=json.loads((case/'receive_ready_summary.json').read_text())
        assert ready['state']=='passed' and ready['notifications']==ready['received']==ready['data_admissions']==1
        assert bridge['completed_packets']==1 and bridge['written_flits']==flits
        assert bridge['aux_written']==bridge['aux_sent']==bridge['aux_credits_returned']==(flits if mode=='static_cs' else 0)
        with (case/'events.csv').open() as f:
            completed=[float(r['time']) for r in csv.DictReader(f) if r['event']=='COMPLETE']
        assert len(completed)==1
        drain=completed[0]
        for filename in ('source.csv','events.csv','receive_events.csv','receive_ready_events.csv','wire_headers.csv'):
            with (case/filename).open() as f:
                for row in csv.DictReader(f):
                    if row.get('time'):drain=max(drain,float(row['time']))
        complete=math.ceil(completed[0]);drain=math.ceil(drain)
        assert issue<=complete<=drain
        self.sequence+=1;self.drained_until=drain
        result=dict(sequence=self.sequence,src=src,dst=dst,bytes=size,issue=issue,receive_complete=complete,
                    drained=drain,mode=mode,descriptor=descriptor,data_flits=flits,actual_ready_controls=1)
        self.events.append(result)
        (case/'completion.json').write_text(json.dumps(result,indent=2)+'\n')
        return result

class CANoCTransport:
    target_noc=True
    def __init__(self,backend,network,native=None):
        self.backend=backend;self.network=network;self.native=native;self.events=[]

    def send_handles(self,source,destination,size,mode='mesh'):
        b=self.backend
        assert source in b.live and destination in b.live
        src,srcbytes,_=b.live[source];dst,dstbytes,_=b.live[destination]
        assert src!=dst and 0<size<=min(srcbytes,dstbytes) and size%32==0
        assert size<=32768, 'first probe supports one bounded packet; no implicit truncation'
        payload=b.get(source,size=size)  # real physical CA-mapped HB read
        issue=b.clock
        measured=self.network.transfer(src,dst,size,issue,mode)
        b.rpc(16,measured['drained'])  # advance real memory clock, no fabricated delay
        assert b.clock>=measured['receive_complete']
        write_start=b.clock;b.put(destination,payload)
        actual=b.get(destination,size=size)
        assert actual==payload
        event=dict(measured,write_start=write_start,consumer_ready=b.clock,
                   payload_sha256=hashlib.sha256(actual).hexdigest(),legacy_noc_invoked=False)
        self.events.append(event)
        return actual

    def send(self,src,dst,token,stage,payload,mode='mesh'):
        b=self.backend;handles=[]
        try:
            source=b.stage(src,payload);handles.append(source)
            destination=b.alloc(dst,len(payload));handles.append(destination)
            result=self.send_handles(source,destination,len(payload),mode)
            self.events[-1].update(token=token,stage=stage,backend='target NoC + actual CA-mapped HB')
            if self.native is not None:self.native.select_partition(dst,stage)
            return result
        finally:
            for handle in reversed(handles):b.free(handle)
