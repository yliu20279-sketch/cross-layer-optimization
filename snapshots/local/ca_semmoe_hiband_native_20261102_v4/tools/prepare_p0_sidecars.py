"""Prepare actual native-hook metadata from an explicit FP16 graph contract.

No default workload, no runner import, no simulation launch. A request map
must be supplied explicitly; old evaluation IDs are never renamed to profile.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.common import require


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--objects',required=True)
    parser.add_argument('--requests',required=True)
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    source=Path(args.objects);req=Path(args.requests);out=Path(args.out)
    require(not out.exists(),'sidecar output exists')
    payload=json.loads(source.read_text(encoding='utf-8'))
    objects=payload['objects'] if isinstance(payload,dict) else payload
    requests=json.loads(req.read_text(encoding='utf-8'))
    require(objects and requests and isinstance(requests,dict),'explicit object/request identities required')
    ids=set();rows=[]
    for obj in objects:
        require(obj['id'] not in ids,'duplicate object ID');ids.add(obj['id'])
        require(obj.get('generation',0)==0,'static hook contract does not certify dynamic paging generations')
        movable=obj.get('role')=='FP16_weight' and not obj['name'].startswith('router_')
        require(obj['partition']>=0 and obj['address']>=0 and obj['bytes']>0,'bad object range')
        rows.append('%d %d %d %d %d %d'%(obj['id'],obj['partition'],obj['address'],obj['bytes'],
                                         obj.get('generation',0),movable))
    names=[]
    for key,value in sorted(requests.items(),key=lambda x:int(x[0])):
        require(int(key)>=0 and isinstance(value,str) and value and all(c.isascii() and (c.isalnum() or c in '_-.:') for c in value),
                'unsafe request ID')
        names.append('%d %s'%(int(key),value))
    out.mkdir()
    (out/'objects.txt').write_text(str(len(rows))+'\n'+'\n'.join(rows)+'\n')
    (out/'requests.txt').write_text(str(len(names))+'\n'+'\n'.join(names)+'\n')
    receipt={'object_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
             'request_source_sha256':hashlib.sha256(req.read_bytes()).hexdigest(),
             'objects':len(rows),'requests':len(names),'dtype':'F16','generation_scope':'static zero only',
             'native_runs':0,'trace_class_must_be_explicit_at_launch':True}
    (out/'MANIFEST.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt))


if __name__=='__main__':main()
