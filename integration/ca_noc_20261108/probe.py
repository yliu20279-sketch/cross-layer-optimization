"""Small real CA physical-mapping / NoC / numerical-consumer integration probe."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import struct
import numpy as np
from transport import load_ca_api,TargetNoC,CANoCTransport

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ca-root',required=True,type=Path)
    ap.add_argument('--build',required=True,type=Path)
    ap.add_argument('--noc',required=True,type=Path)
    ap.add_argument('--graph',required=True,type=Path)
    ap.add_argument('--ram-config',required=True,type=Path)
    ap.add_argument('--npu-config',required=True,type=Path)
    ap.add_argument('--out',required=True,type=Path)
    args=ap.parse_args();out=args.out.resolve();assert not out.exists();out.mkdir(parents=True)
    report=dict(state='running',scope='serialized physical-page/NoC/vector interface probe',
                full_application=False,online_CA_optimization=False,performance_ready=False)
    def save():(out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
    save();backend=None
    try:
        api=load_ca_api(args.ca_root)
        binary=args.build.resolve()/'coupled_backend'
        build=json.loads((args.build/'build_receipt.json').read_text())
        assert sha(binary)==build['binary_sha256']
        backend=api.LiveBackend(binary,sha(binary),out/'ca',args.ram_config.resolve(),
                                controls='off',npu_config=args.npu_config.resolve(),timeout=180)
        network=TargetNoC(args.noc,'e6058e940931db3835c4bef6704354aac10851070bc1e0c1f90b65a3f033278a',args.graph,out/'network')
        transport=CANoCTransport(backend,network)
        values=np.arange(20*4096//4,dtype='<f4')
        source=backend.stage(0,values.tobytes(),role=1)
        target=backend.alloc(5,2048)
        expected=values[:512].tobytes()
        assert transport.send_handles(source,target,2048,'mesh')==expected
        rows,generation=backend.layout()
        assert len(rows)==20 and set(rows[:,3])=={0}
        candidate=rows[:,:3].copy()
        candidate[0,2],candidate[1,2]=int(candidate[1,2]),int(candidate[0,2])
        before=backend.clock
        backend.install_layout(candidate,generation,budget_percent=10)
        after=backend.clock
        assert after>before
        updated,new_generation=backend.layout()
        assert new_generation==generation+1 and np.array_equal(updated[:,:3],candidate)
        assert transport.send_handles(source,target,2048,'static_cs')==expected
        # An actual target numerical primitive consumes the transferred HB object.
        ones=backend.stage(5,np.ones(512,dtype='<f4').tobytes())
        result=backend.alloc(5,2048)
        consumer_start=backend.clock
        backend.rpc(6,target,ones,result,512,0)
        output=backend.get(result)
        assert output==(values[:512]+np.float32(1)).astype('<f4').tobytes()
        assert consumer_start>=transport.events[-1]['consumer_ready']
        for handle in (result,ones,target,source):backend.free(handle)
        summary=backend.close();backend=None
        assert summary['packets']==summary['packet_callbacks']==0,'legacy NoC was also called'
        assert summary['transactions']==summary['callbacks'] and summary['mapping_installs']==1
        assert summary['migration_write_bytes']==8192
        assert len(network.events)==2 and [e['mode'] for e in network.events]==['mesh','static_cs']
        with (out/'ca/LIVE_EVENTS.csv').open() as f:events=list(csv.DictReader(f))
        # Read addresses come from the changed physical frames, not logical copies.
        model_reads=[r for r in events if r['event']=='DRAM_ISSUE' and r['object']==str(source) and r['write']=='0'
                     and r.get('logical_offset')=='0' and r.get('migration')=='0']
        assert len(model_reads)>=2 and int(model_reads[0]['address'])!=int(model_reads[-1]['address'])
        report.update(state='passed',DRAM=summary,transfers=transport.events,
                      mapping=dict(changed_bytes=8192,total_weight_bytes=81920,start=before,complete=after,
                                   generation_before=generation,generation_after=new_generation),
                      consumer=dict(kind='native_FP32_vector_add',elements=512,start=consumer_start,
                                    output_sha256=hashlib.sha256(output).hexdigest(),bitwise_equal=True),
                      physical_source_addresses=[int(r['address']) for r in model_reads],
                      target=dict(NPU=16,capacity_per_partition=2147483648,DRAM_transaction_bytes=32),
                      original_sources_modified=False)
    except BaseException as error:
        report.update(state='failed',reason=repr(error));raise
    finally:
        if backend is not None:backend.abort()
        save()
    print(json.dumps({'state':report['state'],'transfers':len(report['transfers']),'consumer_elements':512}))

if __name__=='__main__':main()
