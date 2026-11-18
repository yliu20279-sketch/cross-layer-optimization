"""Offline byte-level verification; no simulation, network or synthesis."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
def sha(raw):return hashlib.sha256(raw).hexdigest()
manifest=json.loads((R/'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
for name,entry in manifest['files'].items():
 raw=(R/name).read_bytes()
 assert len(raw)==entry['bytes'] and sha(raw)==entry['sha256'],name
s=json.loads((R/'FULL_LATEST_STATUS.json').read_text(encoding='utf-8'))
source=json.loads(s['files']['SOURCE_MANIFEST.json']);matrix=json.loads(s['files']['MATRIX.json'])
assert matrix['status']=='PASS' and matrix['completed']==len(matrix['runs'])==120
assert len(list((R/'results').glob('*.json')))==120
assert len(list((R/'rr_reference').glob('*.json')))==120
assert len(list((R/'cases').glob('*.txt')))==30
assert len({(run['task']['case'],run['task']['arm']) for run in matrix['runs']})==120
for name,h in source['source_sha256'].items():assert sha((R/'package'/name).read_bytes())==h==s['source_actual'][name],name
for c in source['cases']:assert sha((R/'cases'/(c['name']+'.txt')).read_bytes())==c['case_sha256'],c['name']
for run in matrix['runs']:
 assert run['status']=='PASS'
 name=run['name'];raw=(R/'results'/(name+'.json')).read_bytes()
 assert sha(raw)==run['sha256']==s['results'][name]['sha256'] and raw.decode()==s['results'][name]['text'],name
for name,entry in s['rr_reference'].items():
 raw=(R/'rr_reference'/(name+'.json')).read_bytes()
 assert sha(raw)==entry['sha256'] and raw.decode()==entry['text'],name
pre=json.loads((R/'execution_sources/precheck/SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
for name,h in pre['support_sha256'].items():assert sha((R/'execution_sources/precheck'/name).read_bytes())==h,name
extension=json.loads((R/'execution_sources/full/EXTENSION_START.json').read_text(encoding='utf-8'))
assert sha((R/'execution_sources/full/driver.py').read_bytes())==extension['driver_sha256']
assert sha((R/'execution_sources/full/audit_full.py').read_bytes())==extension['audit_sha256']
print(json.dumps({'status':'PASS_OFFLINE_PACKAGE','manifest_files':len(manifest['files']),'results':120,'cases':30,'source_files':len(source['source_sha256']),'experiment_runs_started':0},indent=2))
