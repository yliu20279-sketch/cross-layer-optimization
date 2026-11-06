import hashlib,json,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'onednn_source';D.mkdir(exist_ok=False)
url='https://api.github.com/repos/oneapi-src/oneDNN/git/trees/v3.5.3?recursive=1'
tree=json.load(urllib.request.urlopen(url,timeout=30))['tree'];paths=[v['path'] for v in tree if v['type']=='blob' and v['path'].startswith('src/cpu/x64/gemm/') and ('gemm_info' in v['path'] or 'gemm_driver' in v['path'])];rows=[]
for path in paths:
 source='https://raw.githubusercontent.com/oneapi-src/oneDNN/v3.5.3/'+path;data=urllib.request.urlopen(source,timeout=30).read();p=D/Path(path).name;p.write_bytes(data);rows.append(dict(path=path,local=p.name,url=source,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
(D/'MANIFEST.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows))
