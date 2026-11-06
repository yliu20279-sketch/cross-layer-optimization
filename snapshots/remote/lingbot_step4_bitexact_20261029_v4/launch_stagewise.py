import pathlib,hashlib,json,subprocess
P=pathlib.Path(__file__).resolve().parent
freeze=json.loads((P/'STAGEWISE_PROTOCOL.json').read_text())
for name,h in freeze['files'].items():assert hashlib.sha256((P/name).read_bytes()).hexdigest()==h,name
with (P/'stagewise_supervisor.log').open('wb') as f:c=subprocess.Popen(['/mnt/sda1/h3240101068/lingbot_steps1_2_20261027_v1/venv/bin/python',str(P/'supervise_stagewise.py')],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(P/'STAGEWISE_LAUNCH.json').write_text(json.dumps(dict(pid=c.pid,target_GPU_count=0,client_connection_required=False,CPU_threads=16,nice=10),indent=2));print(c.pid)
