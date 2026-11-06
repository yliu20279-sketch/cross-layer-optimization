from pathlib import Path
import json,subprocess,hashlib
P=Path('/mnt/sda1/h3240101068/swe_qwen3_legosim_integration_20261030_v1');R=P/'unified_layers_fifo_v2'
cfg=json.loads((R/'unified_layers.yml').read_text());phase=cfg['phase2'][0]
phase['args']=[str(P/'phase2_receipt_gate.py'),str(R),phase['cmd']]+phase['args'];phase['cmd']='/usr/bin/python3'
# New config only; never mutate the already-running configuration.
(R/'unified_layers_gated.yml').write_text(json.dumps(cfg,indent=2))
c=subprocess.run(['python3',str(P/'phase2_receipt_gate.py'),str(P/'unified_layers')],capture_output=True,text=True)
assert c.returncode==8
(R/'RECEIPT_GATE_NEGATIVE.json').write_text(json.dumps(dict(state='PASS_NEGATIVE_EOF_RUN_REJECTED',returncode=c.returncode,stdout=c.stdout,config_sha256=hashlib.sha256((R/'unified_layers_gated.yml').read_bytes()).hexdigest(),current_run3_uses_this_config=False),indent=2))
print('gated config prepared; current run3 not changed')
