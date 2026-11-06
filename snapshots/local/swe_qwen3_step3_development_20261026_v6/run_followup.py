"""Bounded diagnosis only; do not replace registered SWE outcomes."""
import json,re,subprocess,traceback
from pathlib import Path
import backend as b
PARENT=Path(__file__).resolve().parent
ROOT=PARENT/'diagnostic_followup'

def main():
    ROOT.mkdir();b.ROOT=ROOT
    backend=b.Backend();backend.instrument();results=[]
    prompt='Write only one Python fenced block defining mean(values). It must return None on an empty list, and the arithmetic mean on nonempty numeric lists. No tools or shell commands.'
    for label,policy in [('greedy',dict(do_sample=False,temperature=None,top_p=None,top_k=None)),('sampling',dict(do_sample=True,temperature=0.7,top_p=0.8,top_k=20))]:
        backend.decoding=policy
        record=backend.generate([dict(role='user',content=prompt)],'direct_mean_'+label,128,True)
        blocks=re.findall(r'```python\s*\n(.*?)\n```',record['text'],re.S)
        if len(blocks)!=1:results.append(dict(mode=label,request=record['request_id'],state='FORMAT_FAILURE'));continue
        out=ROOT/label;out.mkdir();(out/'solution.py').write_text(blocks[0]+'\n')
        (out/'check.py').write_text('from solution import mean\nassert mean([]) is None\nassert mean([2,4,6]) == 4\nassert mean([1,3]) == 2\nprint("PASS_THREE_ASSERTIONS")\n')
        cid=subprocess.check_output(['docker','run','-d','--network','none','--cpus','1','--memory','512m','--pids-limit','128','--label','swe_qwen3_direct_diagnosis=1','-w','/work','codex-aligned-build:20260827-slim','sleep','10m'],text=True).strip()
        try:
            for name in ['solution.py','check.py']:subprocess.run(['docker','cp',str(out/name),cid+':/work/'+name],check=True,capture_output=True,timeout=30)
            p=subprocess.run(['docker','exec',cid,'python3','/work/check.py'],capture_output=True,text=True,timeout=30)
            entry=dict(mode=label,request=record['request_id'],returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,container_id=cid,scope='same synthetic function single turn, not autonomous repair or SWE task')
            b.save(out/'RESULT.json',entry);results.append(entry)
        finally:subprocess.run(['docker','stop','--time','2',cid],capture_output=True,timeout=15)
    b.save(ROOT/'DIRECT_CODE_CONTRAST.json',results)
    real=[json.loads(p.read_text()) for p in (PARENT/'requests').glob('*/REQUEST.json')]
    large=[x for x in real if x['prompt_tokens']>=8192]
    if large:
        stress=max(large,key=lambda x:x['prompt_tokens']);state='PASS_REAL_REQUEST_LONG_PREFILL_NO_OOM';origin='parent registered development request'
    else:
        backend.decoding=dict(do_sample=False,temperature=None,top_p=None,top_k=None)
        stress=backend.generate([dict(role='user',content='Synthetic capacity check. Ignore filler: '+('x '*8192)+'\nReply with exactly READY.')],'synthetic_capacity_8192',2,True)
        state='PASS_SYNTHETIC_LONG_PREFILL_NO_OOM';origin='additional synthetic request'
    b.save(ROOT/'CAPACITY_RESULT.json',dict(state=state,origin=origin,request=stress['request_id'],prompt_tokens=stress['prompt_tokens'],new_tokens=stress['new_tokens'],peak_allocated_bytes=stress['peak_allocated_bytes'],peak_reserved_bytes=stress['peak_reserved_bytes'],scope='observed >=8192-token prefill completed with actual routes; no real-task solve, maximum32K capacity or numerical certification'))
    b.save(ROOT/'STATUS.json',dict(state='DIAGNOSTICS_FINISHED',NPU_runs=0))

if __name__=='__main__':
    try:main()
    except Exception:
        b.save(ROOT/'STATUS.json',dict(state='FAILED_RETAINED',traceback=traceback.format_exc(),NPU_runs=0));raise
