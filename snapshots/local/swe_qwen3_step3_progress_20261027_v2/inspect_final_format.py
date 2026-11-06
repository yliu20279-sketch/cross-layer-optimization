import json,re
from pathlib import Path
R=Path(__file__).resolve().parent;items=[]
for p in sorted((R/'inference'/'development_thinking').glob('*/requests/*/REQUEST.json')):
    rec=json.loads(p.read_text());text=rec['text'];final=text.rsplit('</think>',1)[-1] if '</think>' in text else ''
    blocks=re.findall(r'```([^\n]*)\n(.*?)\n```',final,re.S)
    items.append(dict(task=rec['task_id'],request=p.parent.name,thinking_ended=151668 in rec['new_token_ids'],
        new_tokens=rec['new_tokens'],hit_token_cap=rec['new_tokens']==rec['max_new_tokens'],
        block_labels=[x[0] for x in blocks],final_preview=final[:2400],
        scope='final answer only; no raw reasoning printed'))
(R/'FINAL_FORMAT_DIAGNOSTIC.json').write_text(json.dumps(items,indent=2));print(json.dumps(items[-3:],indent=2))
