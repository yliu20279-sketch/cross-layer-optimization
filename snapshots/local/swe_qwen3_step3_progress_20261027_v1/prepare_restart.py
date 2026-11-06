import json,datetime,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent
assert not (R/'requests').exists()
assert not list(R.glob('development_*/**/REQUEST.json'))
old=R/'startup_interruption';old.mkdir(exist_ok=False)
for name in ['RUN.log','LAUNCH.json']:
    if (R/name).exists():(R/name).rename(old/name)
(old/'REASON.json').write_text(json.dumps(dict(reason='Pre-inference tokenizer-boundary correction: find 151668 in raw tokens before skipping special tokens; own loading PID terminated, no model requests completed',utc=datetime.datetime.now(datetime.timezone.utc).isoformat())))
(R/'METHOD_SNAPSHOT.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(R.glob('*.py'))},indent=2))
