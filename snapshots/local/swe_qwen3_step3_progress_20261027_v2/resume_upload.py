import subprocess,json,time
from pathlib import Path
R=Path(__file__).resolve().parent
attempts=[]
for attempt in range(1,5):
    p=subprocess.run(['sftp','-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=8','-b',str(R/'upload_images.sftp'),'myserver-113'],cwd=R.parent)
    attempts.append(dict(attempt=attempt,returncode=p.returncode))
    (R/'UPLOAD_TRANSPORT_STATUS.json').write_text(json.dumps(dict(state='TRANSPORT_FINISHED_NEEDS_REMOTE_SHA' if p.returncode==0 else 'RETRYABLE_CONNECTION_FAILURE',attempts=attempts),indent=2))
    if p.returncode==0:break
    time.sleep(3)
else:raise RuntimeError('Four bounded SFTP attempts failed; partial files preserved')
