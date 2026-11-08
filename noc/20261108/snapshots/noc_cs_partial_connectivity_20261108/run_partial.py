"""Complete every two/three-output partial matching on each physical CS."""
from pathlib import Path
from itertools import product
import hashlib,json
R=Path(__file__).resolve().parent
source=R/'reference_checker.py'
text=source.read_text()
assert '\nsave()\ntry:' in text
namespace={'__file__':str(R/'run_partial.py'),'__name__':'partial_connectivity_reference'}
exec(compile(text.split('\nsave()\ntry:',1)[0],str(source),'exec'),namespace)
state=namespace['state'];save=namespace['save'];run=namespace['run']
state.update(scope='all two/three-output legal CS partial matchings with receive-ready, Mesh competition, and one SRAM port',
             checker_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
             binary_sha256=hashlib.sha256((R/'popnet_cs_ni').read_bytes()).hexdigest())
assert state['binary_sha256']=='e6058e940931db3835c4bef6704354aac10851070bc1e0c1f90b65a3f033278a'
save()
try:
    choices=[]
    for mapping in product(range(-1,4),repeat=4):
        pairs=[(i,o) for o,i in enumerate(mapping) if i>=0]
        if len(pairs) not in (2,3):continue
        if any(i==o for i,o in pairs) or len({i for i,o in pairs})!=len(pairs):continue
        choices.append(pairs)
    assert len(choices)==86
    for c in range(9):
        for k,pairs in enumerate(choices):run('cs%d_partial%d'%(c,k),c,pairs)
    assert len(state['cases'])==774
    state.update(state='passed',legal_partial_states_per_CS=86,partial_cases=774,
                 combined_with_prior_suite='12 single + 86 partial + 9 full = all 107 nonzero legal states for each CS; all-off is covered in plain Mesh regression',
                 application_performance_claim=False)
except BaseException as e:
    state.update(state='failed',reason=repr(e));save();raise
finally:save()
