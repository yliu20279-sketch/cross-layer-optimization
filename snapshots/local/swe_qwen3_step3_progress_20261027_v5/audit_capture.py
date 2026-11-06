import hashlib,json
from pathlib import Path
import torch
ROOT=Path(__file__).resolve().parent
records=[];incomplete=[]
for folder in sorted((ROOT/'requests').iterdir()):
    if not (folder/'MANIFEST.json').exists():incomplete.append(folder.name);continue
    manifest=json.loads((folder/'MANIFEST.json').read_text())
    for item in manifest:
        p=folder/item['path'];h=hashlib.sha256()
        with p.open('rb') as f:
            while chunk:=f.read(8*1024*1024):h.update(chunk)
        assert p.stat().st_size==item['bytes'] and h.hexdigest()==item['sha256']
    req=json.loads((folder/'REQUEST.json').read_text());forwards=req['forwards']
    assert sum(x['input_tokens'] for x in forwards if x['phase']=='prefill')==req['prompt_tokens']
    assert sum(x['phase']=='decode' for x in forwards)==req['new_tokens']-1
    if req['route_records']:
        routes=torch.load(folder/'actual_routes.pt',weights_only=True,map_location='cpu')
        assert len(routes)==48*len(forwards)
        for i,route in enumerate(routes):
            assert route['layer']==i%48 and route['forward']==i//48
            assert route['selected_experts'].shape==(forwards[i//48]['input_tokens'],8)
            assert int(route['selected_experts'].min())>=0 and int(route['selected_experts'].max())<128
            assert route['final_weights'].dtype==torch.bfloat16 and torch.isfinite(route['final_weights']).all()
        fixtures=torch.load(folder/'layer0_actual_fixtures.pt',weights_only=True,map_location='cpu')
        assert sum(v['forward']['input_tokens'] for v in fixtures['prefill_chunks'].values())==req['prompt_tokens']
        for fixture in list(fixtures['prefill_chunks'].values())+([fixtures['decode']] if 'decode' in fixtures else []):
            assert fixture['decoder_input'].dtype==fixture['decoder_output'].dtype==torch.bfloat16
            assert fixture['router_probabilities_fp32'].dtype==torch.float32
        if req['new_tokens']>1:
            assert fixtures['decode']['layer0_key_cache_before'].shape[-2]==req['prompt_tokens']
            assert fixtures['decode']['layer0_value_cache_before'].dtype==torch.bfloat16
    records.append(dict(request=folder.name,task=req['task_id'],prompt_tokens=req['prompt_tokens'],new_tokens=req['new_tokens'],route_records=req['route_records'],prefill_forwards=sum(f['phase']=='prefill' for f in forwards),peak_allocated_bytes=req['peak_allocated_bytes'],peak_reserved_bytes=req['peak_reserved_bytes']))
(ROOT/'CAPTURE_AUDIT.json').write_text(json.dumps(dict(state='PASS_STRUCTURE_HASH_AND_PHASE' if not incomplete else 'PARTIAL_INCOMPLETE_REQUESTS',requests=records,incomplete_requests=incomplete,scope='byte integrity, actual route coverage, phase accounting and fixture dtypes/KV shape; no layer numerical acceptance or target timing'),indent=2))
