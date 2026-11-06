import pathlib,json,hashlib,tarfile,os,runpy
R=pathlib.Path(__file__).resolve().parent;runpy.run_path(str(R/'capacity_plan.py'),run_name='__main__')
for q in R.rglob('*'):
 if q.is_file():q.chmod(0o644)
 elif q.is_dir():q.chmod(0o755)
a=json.loads((R/'INDEPENDENT_AUDIT.json').read_text());t=json.loads((R/'TP16_O_RESULT.json').read_text());assert not a['failures'] and all(r['BF16_GPU_bit_mismatches']==0 for r in t['rows'] if r['path']=='TP16_serial_FDA_carry')
(R/'FINAL_STATUS.json').write_text(json.dumps(dict(state='PARTIAL_STEP5_EP16_FUNCTIONAL_NOC_SUBSET_AND_O_NUMERICAL',whole_step5=False,target_GPU_count=0,host_GiB=128,HB_GiB=8,independent_checks=a['check_count'],PopNet_records=a['noc_records'],original_TP16_partial_sum_failure_preserved=True,remaining=['full coupled target payload/compute/NoC DAG','TP16 carry full attention lowering','host PCIe/HB pager and actual SRAM lifetime services','full query NoC timing']),indent=2))
members=[q for q in sorted(R.rglob('*')) if q.is_file() and q.suffix!='.npy' and q.name not in ['review.tar.gz','FINAL_MANIFEST.json','FINAL_DELIVERY.json'] and '__pycache__' not in q.parts]
manifest=[dict(file=str(q.relative_to(R)),bytes=q.stat().st_size,sha256=hashlib.sha256(q.read_bytes()).hexdigest()) for q in members];(R/'FINAL_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
with tarfile.open(R/'review.tar.gz','w:gz') as f:
 for q in members+[R/'FINAL_MANIFEST.json']:f.add(q,arcname=str(q.relative_to(R)))
r=dict(archive_sha256=hashlib.sha256((R/'review.tar.gz').read_bytes()).hexdigest(),bytes=(R/'review.tar.gz').stat().st_size,payloads=len(members),scope='compact review; full returned slots and O diagnostic arrays retained on113');(R/'FINAL_DELIVERY.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
