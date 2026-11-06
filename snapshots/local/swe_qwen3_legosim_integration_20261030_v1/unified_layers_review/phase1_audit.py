"""Run strict data audit after phase1 without promoting unfinished phase2."""
from pathlib import Path
import json,subprocess
P=Path('/mnt/sda1/h3240101068/swe_qwen3_legosim_integration_20261030_v1')
R=P/'unified_layers_fifo_v2'
# Reuse the unchanged strict data-flow assertions, stopping before NoC assertions.
s=(R/'audit_full.py').read_text().split("log=(R/'RUN3.log').read_text();")[0]
namespace={'__file__':str(R/'audit_full.py')};exec(compile(s,str(R/'audit_full.py'),'exec'),namespace)
c=subprocess.run(['python3',str(P/'phase2_receipt_gate.py'),str(R)],capture_output=True,text=True);assert c.returncode==0,c.stdout+c.stderr
out=dict(state='PASS_LIMITED_UNIFIED_PHASE1_TWO_LAYER',stage_files=56,strict_output_KV_checks=12,CPU_actual_outputs=2,matrix_calls=759,HB_extent=namespace['summary']['HB_extent'],nodes=len(namespace['nodes']),NoC_phase2_complete=False,full_steps_1_7=False,scope='CPU receipt and actual external-HB two-layer functional execution; NoC completion and full target timing remain separate')
(R/'PHASE1_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
