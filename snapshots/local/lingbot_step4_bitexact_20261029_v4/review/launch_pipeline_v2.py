import pathlib,subprocess,json,os
p=pathlib.Path(__file__).resolve().parent
with (p/'supervisor_v2.log').open('wb') as f:
 child=subprocess.Popen(['/mnt/sda1/h3240101068/lingbot_steps1_2_20261027_v1/venv/bin/python',str(p/'resume_full_context_v2.py')],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(p/'SUPERVISOR_V2_LAUNCH.json').write_text(json.dumps(dict(pid=child.pid,client_connection_required=False,target_GPU_count=0),indent=2));print(child.pid)
