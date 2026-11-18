"""Record the actual toolchain and supporting scripts, without host secrets."""
import hashlib,json,platform,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
def main():
    b=json.loads((R/'CURRENT_BUILD.json').read_text());image=b['image'];versions={}
    for name,cmd in {'verilator':['verilator','--version'],'compiler':['g++','--version'],
        'yosys':['yosys','-V'],'python':['python3','--version'],
        'numpy':['python3','-c','import numpy;print(numpy.__version__)']}.items():
        p=subprocess.run(['docker','run','--rm','--network','none',image,*cmd],capture_output=True,text=True,check=True)
        versions[name]=(p.stdout+p.stderr).splitlines()[0]
    data=dict(image=image,host_architecture=platform.machine(),versions=versions,
        support_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [R/'Dockerfile',*sorted(R.glob('*.py'))] if not p.name.endswith('_local.py') and p.name not in ['build_v2.py','build_bench.py']})
    (R/'TOOLS.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(versions))
if __name__=='__main__':main()
