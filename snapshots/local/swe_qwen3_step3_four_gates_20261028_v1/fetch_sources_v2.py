import base64,hashlib,json,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'onednn_source_v2';D.mkdir(exist_ok=False)
def get(url):return json.load(urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'read-only-source-audit'}),timeout=20))
try:
 tree=get('https://api.github.com/repos/oneapi-src/oneDNN/git/trees/v3.5.3?recursive=1')['tree'];sel=[v for v in tree if v['type']=='blob' and v['path'].startswith('src/cpu/x64/gemm/') and ('gemm_info' in v['path'] or 'gemm_driver' in v['path'])];(D/'SELECTION.json').write_text(json.dumps(sel,indent=2));rows=[]
 for v in sel:
  b=get(v['url']);data=base64.b64decode(b['content']);p=D/Path(v['path']).name;p.write_bytes(data);rows.append(dict(path=v['path'],local=p.name,url=v['url'],bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
 (D/'MANIFEST.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows))
except Exception as e:(D/'FAILURE.json').write_text(json.dumps(dict(error=repr(e))));raise
