import json,shutil
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'data';c=json.loads((R/'CASES.json').read_text());b=json.loads((R/'HOST_BACKING.json').read_text())
shutil.copy2(D/'plan.txt',D/'plan_before_rank_metadata.txt')
(D/'plan.txt').write_text('\n'.join('%d %d %d %s %d %d %s %s'%(v['rank'],v['expert'],v['token'],v['shard'],v['offset'],v['weight_bytes'],D/('N%02d_input.bin'%v['rank']),D/('N%02d_gold.bin'%v['rank'])) for v in c)+'\n')
(D/'shards.txt').write_text('\n'.join('%s %d'%(v['path'],v['bytes']) for v in b['shards'])+'\n')
(R/'ASSET_METADATA_AMENDMENT.json').write_text(json.dumps(dict(scope='plan rank/expert/token and full backing filenames only; no numerical input/reference changed',original_plan_preserved=True),indent=2))
print('asset descriptors ready')
