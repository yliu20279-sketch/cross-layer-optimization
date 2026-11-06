"""Verify complete Top-k routes and paired source identities."""
import argparse,csv,gzip,json
from collections import defaultdict
from pathlib import Path

def validate(root):
    m=json.loads((root/'trace_manifest.json').read_text()); groups=defaultdict(set); counts=defaultdict(int)
    with gzip.open(root/'routing_trace.csv.gz','rt',newline='') as f:
        for r in csv.DictReader(f):
            key=(r['request_id'],int(r['position']),int(r['layer']))
            e=int(r['expert']); assert 0<=e<m['experts'] and e not in groups[key]
            assert 0<=int(r['layer'])<m['layers']
            assert m['context']<=int(r['position'])<m['context']+m['decode']
            assert r['phase']=='decode_cached_teacher_forced' and int(r['count'])==1
            assert 0<=float(r['route_prob'])<=1
            groups[key].add(e); counts[r['request_id']]+=1
    assert len(groups)==m['requests']*m['decode']*m['layers']
    assert all(len(v)==m['top_k'] for v in groups.values())
    assert all(v==m['decode']*m['layers']*m['top_k'] for v in counts.values())
    assert set(counts)=={r['request_id'] for r in m['records']}
    return m,dict(status='PASS',rows=sum(counts.values()),requests=len(counts),groups=len(groups))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--trace-dirs',nargs='+',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); args=ap.parse_args()
    results=[validate(p) for p in args.trace_dirs]
    identity=[[(r['request_id'],r['source_index']) for r in m['records']] for m,a in results]
    assert all(x==identity[0] for x in identity)
    payload={'status':'PASS','paired_sources_match':True,'traces':{str(p):a for p,(m,a) in zip(args.trace_dirs,results)}}
    args.out.write_text(json.dumps(payload,indent=2)+'\n'); print(json.dumps(payload,indent=2))
if __name__=='__main__': main()
