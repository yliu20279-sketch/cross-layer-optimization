import hashlib,json,subprocess,time,traceback
from pathlib import Path
R=Path(__file__).resolve().parent;PY=R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
try:
    for item in json.loads((R/'HOLDOUT_IMAGE_ARCHIVES.json').read_text()):
        p=R/item['archive']
        for _ in range(600):
            if p.exists() and p.stat().st_size==item['archive_bytes']:break
            time.sleep(5)
        else:raise RuntimeError('Image transfer not complete')
        h=hashlib.sha256()
        with p.open('rb') as f:
            while b:=f.read(8*1024*1024):h.update(b)
        assert h.hexdigest()==item['archive_sha256']
        subprocess.run(['docker','load','-i',str(p)],check=True,timeout=300)
    subprocess.run([str(PY),str(R/'verify_images.py')],check=True)
    subprocess.run([str(PY),str(R/'launch.py')],check=True)
except Exception:
    (R/'PREFLIGHT_FAILURE.json').write_text(json.dumps(dict(traceback=traceback.format_exc()),indent=2));raise
