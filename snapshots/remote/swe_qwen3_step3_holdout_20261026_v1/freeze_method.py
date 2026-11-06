import datetime,hashlib,json,os
from pathlib import Path
R=Path(__file__).resolve().parent
OLD=R.parent/'swe_qwen3_step3_gpu_20261026_v1'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(8*1024*1024):h.update(b)
    return h.hexdigest()
if __name__=='__main__':
    assert sha(OLD/'test.parquet')=='7a21f37b8bc179c7db5beeb14e88ac538ba283455c776e6b2535bbfb6e3551b4'
    files=[p for p in sorted(R.iterdir()) if p.suffix in ['.py','.json'] and p.name not in ['FREEZE.json','LAUNCH.json','STATUS.json']]
    data=dict(state='FROZEN_BEFORE_HOLDOUT_PROBLEM_ACCESS',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),user_authorization='批准，方法冻结后读取两项留出任务的问题正文，gold和隐藏测试继续隔离，继续完成步骤3。',files={p.name:sha(p) for p in files},dataset_sha256=sha(OLD/'test.parquet'),agent_prompt_source='run_repair.prompt, unchanged from v6',protected_test_layout_amendment='all existing */tests/* paths, frozen before reading problems',problem_read=False,gold_patch_read=False)
    with (R/'FREEZE.json').open('x') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    print(json.dumps(dict(state=data['state'],utc=data['utc'],files=len(files))))
