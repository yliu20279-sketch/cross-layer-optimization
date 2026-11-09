"""Revision and build checks for v5. No manuscript or experimental claims."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import re
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[1]/'11.9/Algorithm_merge_20261109'
MAIN = ROOT/'main_draft1110_noc_formulation_v5.tex'


def read(p):
    return p.read_text(encoding='utf-8').replace('\r\n', '\n').strip()


old = read(BASE/'main_draft1109_design_algorithm_v4.tex')
new = read(MAIN)
expected = old
changes = [
    ('a configuration algorithm selects compatible switch connections to reduce consumer completion time while accounting for reconfiguration costs and shared endpoint bandwidth.',
     'a configuration algorithm maximizes useful traffic assigned to the reconfigurable network under switch-conflict and shared-resource constraints. A timing check accounts for reconfiguration costs before applying an update.'),
    ('addresses, transfer length, permitted source-CS attachments, and the',
     'addresses, transfer length, packet-to-CS assignments, and the'),
    ("State & CS tuple $q_c$, or the NI transfer's permitted CS attachments.",
     'State & CS tuple $q_c$, or NI packet-to-CS assignments indexed by byte offset.'),
    ('with its permitted source-CS attachments and configuration version.',
     'with its packet-to-CS assignments and configuration version.\n'
     'Each assigned packet is identified by its byte offset; its source-CS\n'
     'attachment is stored as a route tag in the transmit queue. Packets\n'
     'without such an assignment use the Mesh.')]
for a, b in changes:
    assert expected.count(a) == 1, a
    expected = expected.replace(a, b)
assert expected == new, 'Unlisted main-file change'
fragment = read(ROOT/'noc_prediction_configuration.tex')
assert fragment.split(r'\subsection{Reconfiguration Problem}')[0] == read(BASE/'noc_prediction_configuration.tex').split(r'\subsection{Reconfiguration Problem}')[0]
expanded = new.replace(r'\input{noc_prediction_configuration.tex}', fragment)
design = expanded[expanded.index(r'\section{Design}'):expanded.index(r'\section{Evaluation Results and Analysis}')]
active = '\n'.join(line.split('%', 1)[0] for line in design.splitlines())
for label in ['noc-volume-objective', 'noc-binary-variables', 'noc-packet-assignment',
              'noc-path-activation', 'noc-cs-exclusion', 'noc-resource-capacity',
              'noc-switch-mapping', 'noc-switching-check']:
    assert r'\label{eq:'+label+'}' in fragment
assert 'G(S)' not in fragment and r'\max_{\mathbf z,\mathbf x}' in fragment
assert 'u_{m,0,r}' in fragment and '1-\\sum' in fragment
assert 'at most 13 rounds' in fragment
assert active.count(r'\begin{figure*}') == 2
assert active.count(r'\begin{algorithm}') == 1
assert active.count(r'\Comment{') >= 2
assert len(re.findall(r'\\subsection\{', active)) == 6
for term in ['TrialConnection', 'packetnode', 'COMMIT', 'LOAD', 'local_cfg']:
    assert term not in active, term
for term in ['we do not', 'not yet', 'not implemented', 'validated']:
    assert term not in active.lower(), term
labels = re.findall(r'\\label\{([^}]+)\}', expanded)
assert not [k for k, n in Counter(labels).items() if n > 1]
refs = re.findall(r'\\(?:ref|eqref)\{([^}]+)\}', expanded)
assert set(refs) <= set(labels)
bib = read(ROOT/'references.bib')+'\n'+read(ROOT/'thermal_references.bib')
keys = set(re.findall(r'@\w+\s*\{\s*([^,]+),', bib))
cites = {k.strip() for group in re.findall(r'\\cite\{([^}]+)\}', expanded) for k in group.split(',')}
assert cites <= keys
assets = re.findall(r'\\includegraphics(?:\[[\s\S]*?\])?\s*\{([^}]+)\}', expanded)
assert all((ROOT/p).is_file() for p in assets)
assert all((ROOT/p).read_bytes() == (BASE/p).read_bytes() for p in assets)
log = MAIN.with_suffix('.log').read_text(encoding='utf-8', errors='replace')
assert not re.search(r'undefined|multiply defined|Overfull|Fatal error|LaTeX Error', log, re.I)
unit = json.loads((ROOT/'formulation_unit_checks.json').read_text(encoding='utf-8'))
assert unit['status'] == 'PASS'
report = {'status': 'PASS', 'scope': 'v5 manuscript and synthetic constraint checks',
          'main_sha256': hashlib.sha256(MAIN.read_bytes()).hexdigest(),
          'fragment_sha256': hashlib.sha256((ROOT/'noc_prediction_configuration.tex').read_bytes()).hexdigest(),
          'prediction_unchanged': True, 'figures_unchanged': True,
          'outside_Design_changes': ['one abstract objective passage'],
          'decision_variables': ['z_p: path activation', 'x_m_p: whole-packet assignment'],
          'objective': 'max planned useful payload volume on CS paths',
          'switching_check_separate': True, 'unit_checks': unit['count'],
          'pdf_pages': len(PdfReader(MAIN.with_suffix('.pdf')).pages),
          'not_claimed': unit['not_claimed'] + ['submission page budget']}
(ROOT/'v5_check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('PASS: explicit volume objective, packet/path constraints, hardware mapping and unchanged figures; '+str(report['pdf_pages'])+' pages.')
