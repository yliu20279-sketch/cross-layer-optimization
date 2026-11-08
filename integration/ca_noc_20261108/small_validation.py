"""Small correctness matrix on real CA/NPU/DRAM and accepted NoC backends.

Synthetic deterministic payloads are protocol test inputs, not benchmarks.
No performance comparisons or optimization benefit claims are produced.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import itertools
import json
import time
import numpy as np
from transport import load_ca_api, TargetNoC, CANoCTransport

NOCHASH='e6058e940931db3835c4bef6704354aac10851070bc1e0c1f90b65a3f033278a'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def records(path):
    with path.open() as stream:return list(csv.DictReader(stream))

class Suite:
    def __init__(self,args):
        self.args=args;self.out=args.out.resolve();assert not self.out.exists();self.out.mkdir(parents=True)
        self.api=load_ca_api(args.ca_root)
        self.build=json.loads((args.build/'build_receipt.json').read_text())
        self.binary=args.build.resolve()/'coupled_backend'
        assert sha(self.binary)==self.build['binary_sha256'] and sha(args.noc)==NOCHASH
        self.inputs={str(p.resolve()):sha(p) for p in
                     [Path(__file__),Path(__file__).with_name('transport.py'),self.binary,args.noc,
                      args.graph,args.ram_config,args.npu_config]}
        self.inputs.update(self.build['native_inputs'])
        self.inputs.update({row['path']:row['sha256'] for row in self.build['frozen_dependencies']})
        self.state=dict(state='running',scope='serialized CA mapping / target NoC correctness matrix',
                        performance_ready=False,full_application=False,online_CA_policy=False,
                        expected_positive=24,expected_negative=6,positive=[],negative=[],input_sha256=self.inputs)
        self.save()

    def save(self):
        (self.out/'STATUS.json').write_text(json.dumps(self.state,indent=2)+'\n')

    def open(self,case):
        return self.api.LiveBackend(self.binary,self.build['binary_sha256'],case/'ca',
                                   self.args.ram_config.resolve(),controls='off',
                                   npu_config=self.args.npu_config.resolve(),timeout=180)

    @staticmethod
    def payload(seed):
        # Integers divided by powers of two are exactly representable in FP32.
        return (((np.arange(20*4096//4,dtype=np.int32)*17+seed)%257-128).astype('<f4')/np.float32(8)).astype('<f4')

    def positive(self,size,seed,mapping,mode):
        name='bytes%d_seed%d_%s_%s'%(size,seed,mapping,mode)
        case=self.out/name;case.mkdir();b=None
        try:
            b=self.open(case);values=self.payload(seed)
            source=b.stage(0,values.tobytes(),role=1);destination=b.alloc(5,size)
            rows,generation=b.layout();assert len(rows)==20 and set(rows[:,3])=={0}
            expected_mapping=rows[:,:3].copy()
            if mapping=='swap':
                expected_mapping[0,2],expected_mapping[1,2]=int(expected_mapping[1,2]),int(expected_mapping[0,2])
                b.install_layout(expected_mapping,generation,budget_percent=10)
            actual,new_generation=b.layout()
            assert np.array_equal(actual[:,:3],expected_mapping)
            assert new_generation==generation+int(mapping=='swap')
            network=TargetNoC(self.args.noc,NOCHASH,self.args.graph,case/'network')
            transport=CANoCTransport(b,network)
            count=size//4;expected=values[:count].tobytes()
            received=transport.send_handles(source,destination,size,mode)
            assert received==expected
            received_hash=hashlib.sha256(expected).hexdigest()
            term=b.stage(5,np.full(count,np.float32(.5),dtype='<f4').tobytes())
            output=b.alloc(5,size);consumer_start=b.clock
            b.rpc(6,destination,term,output,count,0)
            result=b.get(output)
            assert result==(values[:count]+np.float32(.5)).astype('<f4').tobytes()
            # Raw synthetic payloads stay in the experiment directory, not Git.
            (case/'source_fixture.f32').write_bytes(values.tobytes())
            (case/'received_payload.f32').write_bytes(received)
            (case/'consumer_output.f32').write_bytes(result)
            assert consumer_start>=transport.events[0]['consumer_ready']
            for handle in (output,term,destination,source):b.free(handle)
            summary=b.close();b=None
            assert summary['transactions']==summary['callbacks']
            assert summary['packets']==summary['packet_callbacks']==0
            assert summary['mapping_installs']==int(mapping=='swap')
            assert summary['migration_write_bytes']==(8192 if mapping=='swap' else 0)
            events=records(case/'ca/LIVE_EVENTS.csv')
            issued=[r for r in events if r['event']=='DRAM_ISSUE']
            assert issued and all(0<int(r['bytes'])<=32 for r in issued)
            model_reads=[r for r in issued if int(r['object'])==source and r['write']=='0' and r['migration']=='0']
            assert len(model_reads)==size//32
            frame_map={int(row[1]):int(row[2]) for row in actual}
            for row in model_reads:
                offset=int(row['logical_offset'])
                assert int(row['address'])==frame_map[offset//4096]*4096+offset%4096
            transfer=transport.events[0]
            assert transfer['issue']<=transfer['receive_complete']<=transfer['drained']<=transfer['write_start']<transfer['consumer_ready']<=consumer_start
            validation=dict(name=name,state='passed',bytes=size,seed=seed,mapping=mapping,network=mode,
                            received_sha256=received_hash,output_sha256=hashlib.sha256(result).hexdigest(),
                            output_elements=count,bitwise_equal=True,DRAM_transactions=summary['transactions'],
                            mapping_installs=summary['mapping_installs'],migration_write_bytes=summary['migration_write_bytes'],
                            physical_reads_checked=len(model_reads),legacy_NoC_packets=0,transfer=transfer,
                            consumer_start=consumer_start)
            (case/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
            self.state['positive'].append(validation);self.save();print('PASS '+name,flush=True)
        finally:
            if b is not None:b.abort()

    def negative(self,kind):
        case=self.out/('reject_'+kind);case.mkdir();b=None
        messages={'stale_generation':'stale mapping generation','alias_frame':'mapping physical alias',
                  'over_budget':'mapping exceeds effective-weight budget','foreign_frame':'partition weight frame pool changed',
                  'legacy_transfer':'legacy NoC transfer disabled','backwards_clock':'completion cannot move clock backwards'}
        try:
            b=self.open(case);source=b.stage(0,self.payload(7).tobytes(),role=1)
            rows,generation=b.layout();candidate=rows[:,:3].copy()
            candidate[0,2],candidate[1,2]=int(candidate[1,2]),int(candidate[0,2])
            issue=b.clock
            try:
                if kind=='stale_generation':b.install_layout(candidate,generation+1,10)
                elif kind=='alias_frame':
                    candidate[1,2]=candidate[0,2];b.install_layout(candidate,generation,10)
                elif kind=='over_budget':b.install_layout(candidate,generation,5)
                elif kind=='foreign_frame':
                    candidate[0,2]=999;b.install_layout(candidate,generation,10)
                elif kind=='legacy_transfer':
                    destination=b.alloc(5,32);b.rpc(7,source,destination,32)
                elif kind=='backwards_clock':b.rpc(16,issue-1)
                else:raise ValueError(kind)
            except RuntimeError as error:
                assert messages[kind] in str(error),(kind,str(error))
            else:raise AssertionError('invalid request accepted: '+kind)
            b.abort();b=None
            events=records(case/'ca/LIVE_EVENTS.csv')
            assert not any(r.get('migration')=='1' for r in events)
            mapping_log=(case/'ca/MAPPING_EVENTS.jsonl').read_text()
            assert not mapping_log.strip(),'illegal request partially published a mapping'
            validation=dict(name=kind,state='expected_rejection',reason=messages[kind],
                            no_migration_started=True,no_mapping_published=True)
            (case/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
            self.state['negative'].append(validation);self.save();print('PASS reject_'+kind,flush=True)
        finally:
            if b is not None:b.abort()

    def run(self):
        start=time.monotonic()
        try:
            for values in itertools.product((32,2048,32768),(7,19),('identity','swap'),('mesh','static_cs')):
                self.positive(*values)
            for kind in ('stale_generation','alias_frame','over_budget','foreign_frame','legacy_transfer','backwards_clock'):
                self.negative(kind)
            assert len(self.state['positive'])==24 and len(self.state['negative'])==6
            for size,seed in itertools.product((32,2048,32768),(7,19)):
                group=[r for r in self.state['positive'] if (r['bytes'],r['seed'])==(size,seed)]
                assert len(group)==4 and len({r['output_sha256'] for r in group})==1
                assert len({r['received_sha256'] for r in group})==1
            assert all(sha(Path(p))==value for p,value in self.inputs.items()),'test input changed during suite'
            self.state.update(state='passed',paired_groups_bitwise_equal=6,inputs_unchanged=True,
                              host_elapsed_seconds=round(time.monotonic()-start,3))
        except BaseException as error:
            self.state.update(state='failed',reason=repr(error));raise
        finally:self.save()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('ca-root','build','noc','graph','ram-config','npu-config','out'):
        ap.add_argument('--'+key,required=True,type=Path)
    Suite(ap.parse_args()).run()

if __name__=='__main__':main()
