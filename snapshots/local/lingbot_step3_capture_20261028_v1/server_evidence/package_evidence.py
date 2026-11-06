"""Full raw evidence stays on113; export a declared compact local review bundle."""
import pathlib,json,hashlib,tarfile,collections
import numpy as np
import torch
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step3_capture_20261028_v1')
ASSET=pathlib.Path('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe')
torch.set_num_threads(1)
audit=json.loads((P/'INDEPENDENT_CAPTURE_AUDIT.json').read_text())
assert audit['status']=='PASS_LIMITED_REAL_ROUTE_CAPTURE_AND_FIXTURE_INTEGRITY'
assert json.loads((P/'AUDIT_EXIT.json').read_text())['exit_code']==0
model_headers=json.loads((ASSET/'OPERATOR_GRAPH_HEADER_AUDIT_20261027.json').read_text())
download={x['path']:x for x in json.loads((ASSET/'DOWNLOAD_MANIFEST.json').read_text())}
weight_refs=[]
for row in model_headers['parts']['transformer']:
    if not row['name'].startswith('blocks.0.'):continue
    file='model/transformer/'+row['file'];src=download[file]
    weight_refs.append(dict(**row,canonical_file=str(ASSET/file),file_sha256_expected=src['sha256'],hash_provenance='prior complete weight payload verification; file not rehashed in step3'))
(P/'WEIGHT_REFERENCES.json').write_text(json.dumps(dict(layer=0,source_commit='dd5c231e793406c6a8893e9e4307008a9c2adfe4',weight_revision='f2e538f64afe00cc4ae674db2aeb52e2945edfd5',references=weight_refs),indent=2))

export=P/'review_tiles';export.mkdir(exist_ok=True)
fixtures=json.loads((P/'FIXTURE_MANIFEST.json').read_text());tiles=[]
for r in fixtures:
    if r['file'].endswith('_sorted_positions.pt'):continue
    q=P/r['file'];x=torch.load(q,map_location='cpu',weights_only=True)
    branch='uncond' if '_uncond_' in q.name else 'cond';S=48986 if branch=='uncond' else 49883
    indices=torch.tensor(list(range(32))+list(range(S-32,S)),dtype=torch.long)
    if x.ndim==3 and x.shape[0]==1 and x.shape[1]==S:y=x.index_select(1,indices);axis=1
    elif x.ndim==2 and x.shape[0]==S:y=x.index_select(0,indices);axis=0
    elif r.get('encoding')=='LOSSLESS_ALL_ROWS_BITWISE_EQUAL_VERIFIED':y=x;axis=None
    else:continue
    dst=export/q.name;torch.save(y,dst)
    tiles.append(dict(file=str(dst.relative_to(P)),source_full_file=r['file'],source_full_file_sha256=r['file_sha256'],global_joint_token_indices=indices.tolist() if axis is not None else None,selection_axis=axis,shape=list(y.shape),dtype=str(y.dtype),meaning='rows from full-context source Golden, NOT a truncated-context model run',expanded_shape=r.get('expanded_shape')))
(export/'TILE_INDEX.json').write_text(json.dumps(tiles,indent=2))

exclude={'compact_evidence.tar.gz','compact_evidence.tar.gz.sha256','COMPACT_MANIFEST.json','REMOTE_FULL_FILE_MANIFEST.json','package.log','PACKAGE_EXIT.json'}
full=[q for q in P.rglob('*') if q.is_file() and q.name not in exclude]
manifest={str(q.relative_to(P)):{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted(full)}
(P/'REMOTE_FULL_FILE_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
chosen=[q for q in P.iterdir() if q.is_file() and q.suffix in ['.json','.jsonl','.py','.log','.md','.pt'] and q.name not in ['COMPACT_MANIFEST.json','package.log','PACKAGE_EXIT.json']]
chosen+=list(export.rglob('*.pt'))+[export/'TILE_INDEX.json']
routes=[json.loads(line) for line in (P/'ROUTES.jsonl').read_text().splitlines()]
for r in routes:
    if (r['run']=='probe_on' and r['layer']==0) or (r['run']=='full_on' and (r['step'],r['layer']) in [(0,0),(39,47)]):chosen.append(P/r['file'])
chosen=sorted(set(chosen));rows={str(q.relative_to(P)):{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in chosen}
info=dict(scope='COMPACT_LOCAL_REVIEW_NOT_FULL_RAW_ROUTE_OR_FULL_LAYER_TRANSFER',full_remote_members=len(manifest),full_remote_bytes=sum(x['bytes'] for x in manifest.values()),local_members=len(rows),local_bytes=sum(x['bytes'] for x in rows.values()),files=rows,full_raw_root=str(P),excluded='full routes and full layer Golden remain on113; full SHA inventory included')
(P/'COMPACT_MANIFEST.json').write_text(json.dumps(info,indent=2))
archive=P/'compact_evidence.tar.gz'
with tarfile.open(archive,'w:gz') as t:
    for q in chosen+[P/'COMPACT_MANIFEST.json']:t.add(q,arcname=str(q.relative_to(P)),recursive=False)
h=hashlib.sha256(archive.read_bytes()).hexdigest();(P/'compact_evidence.tar.gz.sha256').write_text(h+'  compact_evidence.tar.gz\n')
print(json.dumps({k:v for k,v in info.items() if k!='files'}));print('archive_bytes',archive.stat().st_size,'sha256',h)
