import pathlib,json,hashlib,tarfile
P=pathlib.Path('lingbot_step4_stagewise_20261030_v5').resolve();q=P/'stagewise_followup_review.tar.gz';expected=(P/'stagewise_followup_review.tar.gz.sha256').read_text().split()[0]
with q.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
assert actual==expected
R=P/'review';R.mkdir(exist_ok=True)
with tarfile.open(q,'r:gz') as tf:
 for m in tf.getmembers():assert not m.name.startswith('/') and '..' not in pathlib.PurePosixPath(m.name).parts and not m.issym() and not m.islnk()
 tf.extractall(R,filter='data')
rows=[]
for a in sorted(R.rglob('*')):
 if a.is_file():
  with a.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
  rows.append(dict(file=str(a.relative_to(R)),bytes=a.stat().st_size,sha256=h))
(P/'REVIEW_MANIFEST.json').write_text(json.dumps(dict(scope='compact followup evidence, not full weights/math tables/query outputs',payload_files=len(rows),payload_bytes=sum(r['bytes'] for r in rows),files=rows),indent=2),encoding='utf-8');receipt=dict(status='PASS_LOCAL_REVIEW_ARCHIVE_SHA256',archive_sha256=actual,archive_bytes=q.stat().st_size,payload_files=len(rows),payload_bytes=sum(r['bytes'] for r in rows),whole_layer_complete=False);(P/'LOCAL_VERIFICATION.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
for n in ['SPLITK6_CPU_RESULT.json','FFN_REPAIR_V2_RESULT.json','STAGEWISE_PREFLIGHT.json','STAGEWISE_PROGRESS_SNAPSHOT.json','STAGEWISE_PROTOCOL.json','STAGEWISE_LAUNCH.json']:(P/n).write_bytes((R/n).read_bytes())
status=dict(state='PARTIAL_STAGEWISE_ACCEPTANCE_RUNNING',target_GPU_count=0,host_GiB=128,HB_GiB=8,precision='original mixed BF16/FP32',legacy_failure_preserved=True,legacy_failure_FFN_bits=4,isolated_repaired_FFN_bits=0,reusable_attention_FFN_input_rows=11776,preflight_checks=1660,new_geometry_negative_controls=4,whole_layer_complete=False,new_external_GPU_reference_jobs=3,cumulative_v4_v5_external_GPU_reference_jobs=10,new_target_native_runs=0,LingBot_prior_target_native_runs=1,physical_NPU_runs=0,remote_state_path='/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4/full_layer_stagewise_v1/STATUS.json',progress_snapshot=json.loads((R/'STAGEWISE_PROGRESS_SNAPSHOT.json').read_text()));(P/'STATUS.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
print(json.dumps(receipt))
