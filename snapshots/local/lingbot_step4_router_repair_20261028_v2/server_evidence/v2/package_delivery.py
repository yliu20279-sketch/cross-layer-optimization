import pathlib,json,hashlib,tarfile
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_router_repair_20261028_v2')
V1=P.parent/'lingbot_step4_functional_20261028_v1'
def sha(q):
    with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert json.loads((V1/'INDEPENDENT_AUDIT.json').read_text())['status']=='PASS_EVIDENCE_INTEGRITY_NUMERICAL_RESULT_REMAINS_PARTIAL'
assert json.loads((P/'INDEPENDENT_REPAIR_AUDIT.json').read_text())['status']=='PASS_INDEPENDENT_NUMPY_ROUTER_SELECTION_REDUCTION_RNE_AUDIT'
assert json.loads((P/'INDEPENDENT_FUNCTIONAL_AUDIT.json').read_text())['status']=='PASS_V2_EVIDENCE_INTEGRITY_NUMERICAL_RESULT_REMAINS_PARTIAL'
exclude={'package.log','COMPACT_MANIFEST.json','REMOTE_FILE_MANIFEST.json','delivery.tar.gz','delivery.tar.gz.sha256'}
full={};chosen={}
for tag,root in [('v1',V1),('v2',P)]:
    for q in sorted(root.rglob('*')):
        if not q.is_file() or '__pycache__' in q.parts or q.name in exclude:continue
        name=tag+'/'+str(q.relative_to(root))
        row=dict(bytes=q.stat().st_size,sha256=sha(q));full[name]=row
        rel=q.relative_to(root)
        if len(rel.parts)==1 or rel.parts[0] in ['native_router','repair_outputs'] or (rel.parts[0]=='outputs' and (q.name.startswith('review_') or q.name.endswith('_ids.pt') or q.name.endswith('_weights.pt') or 'selected_global_rows' in q.name)):
            chosen[name]=(q,row)
(P/'REMOTE_FILE_MANIFEST.json').write_text(json.dumps(full,indent=2))
q=P/'REMOTE_FILE_MANIFEST.json';chosen['v2/'+q.name]=(q,dict(bytes=q.stat().st_size,sha256=sha(q)))
info=dict(scope='COMPACT_TWO_RUN_REVIEW_NOT_FULL_CPU_OUTPUT_TRANSFER',full_remote_files=len(full),full_remote_bytes=sum(r['bytes'] for r in full.values()),local_files=len(chosen),local_bytes=sum(r['bytes'] for _,r in chosen.values()),files={n:r for n,(_,r) in chosen.items()},full_output_roots=dict(v1=str(V1),v2=str(P)),excluded='Full CPU norm/FFN-input/FP32 router candidates stay113; complete file SHA inventory included. Original step3 Golden remains canonical on113.')
(P/'COMPACT_MANIFEST.json').write_text(json.dumps(info,indent=2))
a=P/'delivery.tar.gz'
with tarfile.open(a,'w:gz') as t:
    for name,(q,_) in chosen.items():t.add(q,arcname=name,recursive=False)
    t.add(P/'COMPACT_MANIFEST.json',arcname='COMPACT_MANIFEST.json',recursive=False)
h=sha(a);(P/'delivery.tar.gz.sha256').write_text(h+'  delivery.tar.gz\n')
print(json.dumps({k:v for k,v in info.items() if k!='files'}));print('archive_bytes',a.stat().st_size,'sha256',h)
