"""Independent raw-evidence audit; no import of the integration/NumPy kernels."""
from pathlib import Path
import argparse
import csv
import hashlib
import itertools
import json
import struct

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):
    with p.open() as f:return list(csv.DictReader(f))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',required=True,type=Path)
    args=ap.parse_args();root=args.run.resolve()
    status=json.loads((root/'STATUS.json').read_text());assert status['state']=='passed'
    assert all(sha(Path(p))==digest for p,digest in status['input_sha256'].items())
    checked=[];pairs={};dram_total=0
    for size,seed,mapping,mode in itertools.product((32,2048,32768),(7,19),('identity','swap'),('mesh','static_cs')):
        name='bytes%d_seed%d_%s_%s'%(size,seed,mapping,mode);case=root/name
        result=json.loads((case/'validation.json').read_text());assert result['state']=='passed'
        fixture=(case/'source_fixture.f32').read_bytes()
        received=(case/'received_payload.f32').read_bytes()
        output=(case/'consumer_output.f32').read_bytes()
        assert len(fixture)==81920 and len(received)==len(output)==size
        assert received==fixture[:size]
        values=struct.unpack('<%df'%(size//4),received)
        expected=struct.pack('<%df'%len(values),*(v+.5 for v in values))
        assert output==expected,'numerical consumer differs: '+name
        assert hashlib.sha256(output).hexdigest()==result['output_sha256']
        pairs.setdefault((size,seed),set()).add(hashlib.sha256(output).hexdigest())
        ca=case/'ca';events=rows(ca/'LIVE_EVENTS.csv')
        issued={int(r['id']):r for r in events if r['event']=='DRAM_ISSUE'}
        completed={int(r['id']):r for r in events if r['event']=='DRAM_DONE'}
        assert len(issued)==sum(r['event']=='DRAM_ISSUE' for r in events)
        assert len(completed)==sum(r['event']=='DRAM_DONE' for r in events)
        assert issued.keys()==completed.keys()
        for ident,a in issued.items():
            b=completed[ident]
            assert 0<int(a['bytes'])<=32
            assert all(a[k]==b[k] for k in ('rank','address','bytes','write','object','generation','logical_offset','migration'))
            assert float(b['time'])>=float(a['time'])
        dram_total+=len(issued)
        moved=[r for r in issued.values() if r['migration']=='1']
        for write in ('0','1'):
            assert sum(int(r['bytes']) for r in moved if r['write']==write)==(8192 if mapping=='swap' else 0)
        model_reads=[r for r in issued.values() if r['object']=='1' and r['write']=='0' and r['migration']=='0']
        assert len(model_reads)==size//32
        for r in model_reads:
            offset=int(r['logical_offset']);page=offset//4096
            frame=1-page if mapping=='swap' and page<2 else page
            assert int(r['address'])==frame*4096+offset%4096
        assert not any(r['event'].startswith('NOC_') for r in events),'old network also used'
        net=case/'network/transfer_0000'
        bridge=json.loads((net/'bridge_summary.json').read_text())
        ready=json.loads((net/'receive_ready_summary.json').read_text())
        assert bridge['completed_packets']==1 and bridge['written_flits']==size//32+1
        assert bridge['aux_written']==bridge['aux_sent']==bridge['aux_credits_returned']==(size//32+1 if mode=='static_cs' else 0)
        assert ready['state']=='passed' and ready['notifications']==ready['received']==ready['data_admissions']==1
        actual_complete=[float(r['time']) for r in rows(net/'events.csv') if r['event']=='COMPLETE']
        transfer=result['transfer'];assert actual_complete==[transfer['receive_complete']]
        assert transfer['receive_complete']<=transfer['drained']<=transfer['write_start']<transfer['consumer_ready']<=result['consumer_start']
        lowering=[json.loads(line) for line in (ca/'VECTOR_LOWERING.jsonl').read_text().splitlines()]
        assert len(lowering)==1 and lowering[0]['n']==size//4
        assert lowering[0]['begin']==result['consumer_start'] and lowering[0]['complete']>=lowering[0]['begin']
        checked.append(dict(name=name,DRAM_transactions=len(issued),output_sha256=sha(case/'consumer_output.f32')))
    assert len(checked)==24 and len(pairs)==6 and all(len(h)==1 for h in pairs.values())
    for rejection in status['negative']:
        case=root/('reject_'+rejection['name'])
        assert rejection['reason'] in (case/'ca/backend.stderr').read_text()
        assert not any(r['migration']=='1' for r in rows(case/'ca/LIVE_EVENTS.csv'))
        assert not (case/'ca/MAPPING_EVENTS.jsonl').read_text().strip()
    assert len(status['negative'])==6
    report=dict(state='passed',positive_cases=24,negative_cases=6,paired_bitwise_groups=6,
                DRAM_transactions_checked=dram_total,independent_numeric_checker='Python struct; no integration or NumPy import',
                actual_NoC_completion_and_Credit_checks=True,physical_read_addresses_and_callbacks_checked=True,
                suite_status_sha256=sha(root/'STATUS.json'),audit_source_sha256=sha(Path(__file__)),
                full_application=False,performance_ready=False,cases=checked)
    (root/'INDEPENDENT_AUDIT.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'}))

if __name__=='__main__':main()
