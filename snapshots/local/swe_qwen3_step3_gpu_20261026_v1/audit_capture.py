import hashlib,json
from pathlib import Path
import torch
root=Path(__file__).resolve().parent
records=[]
for folder in sorted((root/'requests').iterdir()):
    if not (folder/'MANIFEST.json').exists():continue
    manifest=json.loads((folder/'MANIFEST.json').read_text())
    for item in manifest:
        p=folder/item['path']
        assert p.stat().st_size==item['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']
    req=json.loads((folder/'REQUEST.json').read_text())
    if req['route_records']:
        routes=torch.load(folder/'actual_routes.pt',weights_only=True,map_location='cpu')
        assert len(routes)==48*len(req['forwards'])
        for r in routes:
            assert r['final_weights'].dtype==torch.bfloat16
            assert r['selected_experts'].shape[-1]==8
            assert int(r['selected_experts'].min())>=0 and int(r['selected_experts'].max())<128
    records.append(dict(request=folder.name,route_records=req['route_records'],forwards=len(req['forwards']),manifest_members=len(manifest)))
(root/'CAPTURE_AUDIT.json').write_text(json.dumps(dict(state='PASS_ARTIFACT_STRUCTURE_ONLY',requests=records,scope='file hashes, actual route count/shape/dtype; no numeric layer acceptance or target timing'),indent=2))
