"""Read-only readiness audit at the host holding the frozen runtime artifacts."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.readiness import preflight
from core.phase_gates import source_gate
coverage = json.loads((ROOT/'contracts/implementation_coverage.json').read_text())
out = {}
for model, prefix in [('qwen3', 'Q3'), ('qwen15', 'Q15')]:
    contract = json.loads((ROOT/('contracts/'+model+'.json')).read_text())
    out[model] = {'source': source_gate(contract, [x for x in coverage if x['id'].startswith((prefix, 'C-'))]),
                  'performance': preflight(contract)}
(ROOT/'evidence/REMOTE_GATES.json').write_text(json.dumps(out, indent=2))
print(json.dumps(out))
