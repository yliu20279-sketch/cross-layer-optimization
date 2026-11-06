import json
from pathlib import Path
import backend as b
r=Path(__file__).resolve().parent
old=json.loads((r.parent/'swe_qwen3_step3_repair_20261026_v2/requests/R0004/REQUEST.json').read_text())
class Replay:
    def generate(self,*args):return dict(text=old['text'],request_id='saved_v2_R0004',prompt_tokens=236,new_tokens=31)
m=b.LocalModel(Replay(),'regression',512)
action=m.query([])['extra']['actions']
assert action==[dict(command='cat /work/*.py')],action
obs=m.format_observation_messages({},[dict(output='CHECK_STDOUT',returncode=9,exception_info='CHECK_EXCEPTION')])[0]['content']
assert all(x in obs for x in ['CHECK_STDOUT','CHECK_EXCEPTION','<returncode>9</returncode>'])
(r/'ADAPTER_REGRESSION.json').write_text(json.dumps(dict(state='PASS',saved_previously_rejected_response_parsed=action,exception_and_stdout_and_returncode_visible=True,GPU_initialized=b.torch.cuda.is_initialized()),indent=2))
