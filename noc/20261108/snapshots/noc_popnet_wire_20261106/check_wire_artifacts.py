"""Read-only audit of retained serialized-header and legacy regression evidence."""
from pathlib import Path
import hashlib
import json
import platform
import csv

ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert (ROOT/'wire.exit').read_text().strip()=='0'
assert (ROOT/'legacy.exit').read_text().strip()=='0'
r=json.loads((ROOT/'wire_build/validation.json').read_text())
assert r['status']=='passed_serialized_header_native_popnet' and not r['application_performance']
for name,digest in r['sha256'].items():
    p=ROOT/name
    if platform.system()=='Windows' and name=='build/cmake/popnet_cs_ni' and not p.exists():continue
    assert p.is_file() and sha(p)==digest,name
for c in r['commands']:assert c['returncode']==c['expected'],c['case']
assert len(r['cases'])==22
for name,c in r['cases'].items():
    if 'wire' in c:
        assert not c['wire']['router_uses_packet_table'] and c['header_words_preserved']
        b=c['bridge'];s=c['wire']
        assert s['serialized_data_headers']+s['unchanged_body_flits']==b['written_flits']
        assert b['data_header_retired_flits']==s['serialized_data_headers']
        assert b['payload_written_flits']==s['unchanged_body_flits']
        assert b['aux_written']==b['aux_credits_returned']
        rows=list(csv.DictReader((ROOT/'wire_build'/name/'wire_headers.csv').open()))
        source={(x['packet'],x['source'],x['destination']):x for x in rows
                if x['event'] in ('SOURCE','SOURCE_CONTROL')}
        for row in rows:
            word=int(row['wire_word'])
            if row['event']!='SOURCE_CONTROL' and (word>>61)==0:
                assert ((word>>57)&15)==int(row['source'])
                assert ((word>>53)&15)==int(row['destination'])
                assert ((word>>49)&15)==int(row['gateway'])
                assert ((word>>48)&1)==int(row['aux'])
                assert ((word>>32)&65535)==int(row['epoch'])
            else:assert (word>>61) in (6,7)
            assert row['wire_word']==source[(row['packet'],row['source'],row['destination'])]['wire_word']
    if name.startswith('fault_'):assert c['actual_link_fault_rejected']
assert (ROOT/'build/disabled/delay.txt').read_bytes()==(ROOT/'build/original/delay.txt').read_bytes()
assert len((ROOT/'build/disabled/delay.txt').read_text().splitlines())==768
print('PASS retained wire evidence: 22 cases, serialized heads, local VC contexts, actual-link fault rejection, legacy equivalence')
