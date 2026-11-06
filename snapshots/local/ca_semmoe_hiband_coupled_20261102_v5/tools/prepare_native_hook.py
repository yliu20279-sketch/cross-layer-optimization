"""Generate an instrumented fork of a read-only existing FP16 native interface.

This only prepares source, it does not invoke a simulator. The fork retains
the old timing/scheduling scope; Sem-MoE/HiBand are NOT certified by this hook.
"""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
records=json.loads((ROOT/'evidence/NATIVE_SOURCE_INPUTS.json').read_text(encoding='utf-8'))
byname={Path(row['path']).name:row for row in records}
text=byname['native_main.cc']['text']
text=text.replace('#include <array>', '#include "p0_event_sink.h"\n#include <array>', 1)
text=text.replace('#include "/mnt/sda1/h3240101068/selector_real_v2_phase_engine_20261020_v1/phase_engine.h"',
                  '#include "phase_engine.h"')
anchor='SRGen rng;configuration config(argc,argv);'
assert text.count(anchor)==1
text=text.replace(anchor,'p0::EventSink p0sink(out+"/ca_weight_events.jsonl",envs("P0_OBJECTS"),envs("P0_REQUESTS"),envs("P0_MODEL_DTYPE"),envs("P0_TRACE_CLASS"));\n '+anchor)
capture='[&,i,rank,token,a,bytes,wr](Ramulator::Request&){auto&q=rs[i];'
assert text.count(capture)==2
text=text.replace(capture,'[&,i,rank,token,a,bytes,wr,object=t.object](Ramulator::Request&){auto&q=rs[i];p0sink.callback(rank,object,q.credit,token,wr,nextdram);')
accept='op.accept(t);++issued;'
assert text.count(accept)==2
text=text.replace(accept,'op.accept(t);p0sink.accept(r.request,rank,t.object,r.credit,token,t.address,bytes,wr,now);++issued;')
anchor='require(issued==callbacks&&packets.empty(),"backend not drained");'
assert text.count(anchor)==1
text=text.replace(anchor,'p0sink.finish();'+anchor)
(ROOT/'runtime/native_main_fp16_hook.cc').write_text(text,encoding='utf-8')
for name in ('tiled_phase.h','phase_engine.h'):
    (ROOT/'runtime'/name).write_text(byname[name]['text'],encoding='utf-8')
manifest={'scope':'existing FP16 full-transaction substrate + actual successful accept/callback hook',
          'sem_moe_native_verified':False,'hiband_native_verified':False,'model_forward':False,
          'input_sources':[{k:row[k] for k in ('path','sha256')} for row in records],
          'generated_sha256':hashlib.sha256(text.encode()).hexdigest(),
          'required_sidecars':['P0_OBJECTS','P0_REQUESTS','P0_MODEL_DTYPE=F16','P0_TRACE_CLASS=profile|eval']}
(ROOT/'evidence/NATIVE_HOOK_SOURCE.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'source':'runtime/native_main_fp16_hook.cc','sha256':manifest['generated_sha256']}))
