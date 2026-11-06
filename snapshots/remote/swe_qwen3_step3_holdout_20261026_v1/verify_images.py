import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;out=[]
for image in json.loads((R/'HOLDOUT_IMAGE_ARCHIVES.json').read_text()):
    h=hashlib.sha256()
    with (R/image['archive']).open('rb') as f:
        while b:=f.read(8*1024*1024):h.update(b)
    assert h.hexdigest()==image['archive_sha256']
    info=json.loads(subprocess.check_output(['docker','image','inspect',image['repository']+':latest']))[0]
    assert info['Id']==image['config_digest']
    out.append(dict(instance_id=image['task'],image_id=info['Id'],archive_sha256=h.hexdigest(),diff_ids=info['RootFS']['Layers']))
(R/'IMAGE_VERIFICATION.json').write_text(json.dumps(dict(state='PASS',images=out),indent=2))
