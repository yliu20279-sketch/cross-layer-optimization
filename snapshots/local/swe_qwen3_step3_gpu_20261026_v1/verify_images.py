import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
records=[]
registration=json.loads((R/'TASK_REGISTRATION.json').read_text())['tasks']
for item in json.loads((R/'DEV_IMAGE_ARCHIVES.json').read_text()):
    p=R/item['archive'];h=hashlib.sha256()
    with p.open('rb') as f:
        while chunk:=f.read(8*1024*1024):h.update(chunk)
    assert h.hexdigest()==item['archive_sha256'] and p.stat().st_size==item['archive_bytes']
    image=json.loads(subprocess.check_output(['docker','image','inspect',item['repository']+':latest']))[0]
    assert image['Id']==item['config_digest']
    command=['docker','run','--network','none','--cpus','1','--memory','1g','--pids-limit','256','--label','swe_qwen3_step3_imagecheck=1','-w','/testbed',item['repository']+':latest','git','rev-parse','HEAD']
    result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    expected=next(x['base_commit'] for x in registration if x['instance_id']==item['task'])
    assert result.returncode==0,result.stderr
    present=subprocess.run(command[:-3]+['git','cat-file','-t',expected],capture_output=True,text=True,timeout=60)
    assert present.returncode==0 and present.stdout.strip()=='commit',present.stderr
    records.append(dict(task=item['task'],image_id=image['Id'],image_initial_HEAD=result.stdout.strip(),registered_base_commit=expected,registered_commit_present=True,requires_explicit_reset_before_agent=True,rootfs_diff_ids=image['RootFS']['Layers'],archive_sha256=h.hexdigest()))
(R/'IMAGE_VERIFICATION.json').write_text(json.dumps(dict(state='PASS_IMAGE_IDENTITY_BASE_COMMIT',records=records),indent=2))
