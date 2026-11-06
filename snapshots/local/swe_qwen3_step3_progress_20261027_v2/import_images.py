import json,hashlib,subprocess,traceback
from pathlib import Path
R=Path(__file__).resolve().parent
try:
    for item in json.loads((R/'HOLDOUT_IMAGE_ARCHIVES.json').read_text()):
        p=R/item['archive'];assert p.stat().st_size==item['archive_bytes']
        h=hashlib.sha256()
        with p.open('rb') as f:
            while chunk:=f.read(8*1024*1024):h.update(chunk)
        assert h.hexdigest()==item['archive_sha256']
        (R/'IMAGE_IMPORT_STATUS.json').write_text(json.dumps(dict(state='IMPORTING',task=item['task'])))
        subprocess.run(['docker','load','-i',str(p)],check=True)
    subprocess.run([str(R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'),str(R/'verify_images.py')],check=True)
    (R/'IMAGE_IMPORT_STATUS.json').write_text(json.dumps(dict(state='COMPLETE_VERIFIED')))
except Exception:
    (R/'IMAGE_IMPORT_STATUS.json').write_text(json.dumps(dict(state='FAILED',traceback=traceback.format_exc())));raise
