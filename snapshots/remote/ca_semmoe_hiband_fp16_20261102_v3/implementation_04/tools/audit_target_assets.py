"""Actual FP16 object span audit; no forward or simulator invocation."""
from pathlib import Path
import hashlib
import json
import sys
import argparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.artifacts import TargetArtifactStore
from core.common import require

parser=argparse.ArgumentParser()
parser.add_argument('--assets',required=True)
args=parser.parse_args()
asset=Path(args.assets)
complete=json.loads((asset/'COMPLETE.json').read_text())
manifest=json.loads((asset/'TARGET_MANIFEST.json').read_text())
require(hashlib.sha256((asset/'TARGET_MANIFEST.json').read_bytes()).hexdigest()==complete['target_manifest_sha256'],
        'target manifest changed')
store=TargetArtifactStore(manifest)
require(sum(x['bytes'] for x in manifest)==complete['target_valid_bytes'],'byte ledger differs')
checks=0
for obj in manifest:
    size=obj['bytes']
    tests=[(0,min(64,size)),(max(0,size-31),min(31,size))]
    if size>4106:tests.append((4090,16))
    for offset,n in tests:
        value=store.read(obj['name'],offset,n)
        require(len(value)==n,'short actual target span')
        checks+=1
shared=[]
for obj in manifest:
    if len(obj['parts'])<=1:continue
    h=hashlib.sha256()
    for offset in range(0,obj['bytes'],1024**2):
        h.update(store.read(obj['name'],offset,min(1024**2,obj['bytes']-offset)))
    require(h.hexdigest()==obj['payload_sha256'],'reused shared TP assembly differs')
    shared.append({'name':obj['name'],'exact_payload_sha256':h.hexdigest()})
require(all(row['dtype']=='F16' for row in store.served_segments),'non-FP16 operand served')
receipt={'status':'PASS_REAL_ASSET_BYTE_SERVICE_SCOPED','objects':len(manifest),'span_checks':checks,
         'shared_reconstructions':shared,'served_bytes':store.served_bytes,
         'served_segments':len(store.served_segments),'runtime_packed_tensor_reads':0,
         'full_model_forward':False,'native_simulations':0,'target_valid_bytes':complete['target_valid_bytes']}
(ROOT/'ASSET_BYTE_SERVICE_AUDIT.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
