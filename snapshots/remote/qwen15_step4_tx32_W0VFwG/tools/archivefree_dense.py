"""Detach already-FP16 dense/bias spans from source GPTQ archives, no decode."""
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path('/mnt/sda1/h3240101068/ca_semmoe_hiband_fp16_20261102_v3')
sys.path.insert(0,str(ROOT/'implementation_02'))
from core.artifacts import TargetArtifactStore
from core.common import require

asset=ROOT/'decoded_assets'
source=Path('/mnt/sdb1/h3240101068/models/Qwen1.5-MoE-A2.7B-Chat-GPTQ-Int4')
manifest=json.loads((asset/'TARGET_MANIFEST.json').read_text())
store=TargetArtifactStore(manifest)
output=asset/'dense_archivefree'
require(not output.exists(),'refuse overwrite archive-free output')
output.mkdir()
detached=[]
for i,obj in enumerate(manifest):
    if not any(str(Path(part['file'])).startswith(str(source)+'/') for part in obj['parts']):continue
    path=output/('dense_%04d.f16'%i);h=hashlib.sha256()
    with path.open('xb') as handle:
        for offset in range(0,obj['bytes'],1024**2):
            block=store.read(obj['name'],offset,min(1024**2,obj['bytes']-offset))
            h.update(block);handle.write(block)
    require(h.hexdigest()==obj['payload_sha256'],'detached payload differs')
    obj['parts']=[{'file':str(path),'offset':0,'dtype':'F16','shape':obj['shape'],
                   'bytes':obj['bytes'],'container':'raw_fp16','sha256':h.hexdigest()}]
    obj['runtime_quantized']=False
    detached.append({'name':obj['name'],'file':str(path),'bytes':obj['bytes'],'sha256':h.hexdigest()})
require(len(detached)==171,'expected 99 dense tensors and 72 nonzero biases')
require(not any(str(Path(p['file'])).startswith(str(source)+'/') for o in manifest for p in o['parts']),
        'runtime GPTQ archive dependency remains')
new=asset/'TARGET_MANIFEST_ARCHIVEFREE.json'
require(not new.exists(),'refuse overwrite manifest')
new.write_text(json.dumps(manifest,indent=2)+'\n')
reader=TargetArtifactStore(manifest)
checks=0
for obj in manifest:
    for offset,n in [(0,min(32,obj['bytes'])),(max(0,obj['bytes']-17),min(17,obj['bytes']))]:
        require(len(reader.read(obj['name'],offset,n))==n,'detached span unavailable');checks+=1
receipt={'status':'PASS_ARCHIVEFREE_FP16_TARGET','detached_objects':len(detached),
         'detached_bytes':sum(x['bytes'] for x in detached),'objects':len(manifest),'span_checks':checks,
         'target_manifest_sha256':hashlib.sha256(new.read_bytes()).hexdigest(),
         'target_valid_bytes':sum(x['bytes'] for x in manifest),'runtime_gptq_archive_dependencies':0,
         'detached_files':detached,'native_simulations':0,'model_forwards':0}
(asset/'ARCHIVEFREE_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:v for k,v in receipt.items() if k!='detached_files'}))
