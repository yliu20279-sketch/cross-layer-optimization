import pathlib,subprocess,json,hashlib
p=pathlib.Path(__file__).resolve().parent
assert json.loads((p/'CONNECTED_BLOCK_V2_RESULT.json').read_text())['status']=='PASS_LIMITED_CONNECTED64_FULL_CONTEXT'
assert json.loads((p/'INDEPENDENT_AUDIT.json').read_text())['status']=='PASS_EVIDENCE_AUDIT_LIMITED_FUNCTIONAL_SCOPE'
with (p/'all_queries.log').open('wb') as f:child=subprocess.Popen(['timeout','43200','/mnt/sda1/h3240101068/lingbot_steps1_2_20261027_v1/venv/bin/python',str(p/'validate_all_queries.py')],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(p/'ALL_QUERY_LAUNCH.json').write_text(json.dumps(dict(pid=child.pid,target_GPU_count=0,client_connection_required=False,CPU_threads=16,nice=10,timeout_seconds=43200,source_sha256=hashlib.sha256((p/'validate_all_queries.py').read_bytes()).hexdigest()),indent=2));print(child.pid)
