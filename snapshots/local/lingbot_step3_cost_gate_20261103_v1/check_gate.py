import json
from completion_gate import CompletionGate, KINDS


def rejects(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('invalid receipt accepted')


checks = 0
for cfg in ('cond', 'uncond'):
    identity = dict(request='example_4', cfg=cfg, step=0, layer=0, token=0, version=1)
    expected = {kind: index for index, kind in enumerate(sorted(KINDS))}
    for delayed in sorted(KINDS):
        gate = CompletionGate(identity, expected)
        rejects(lambda: gate.release(1000))
        rejects(lambda: gate.accept(delayed, dict(identity, cfg='wrong'),
                                    expected[delayed], 1, '1'))
        rejects(lambda: gate.accept(delayed, identity, -1, 1, '1'))
        for kind in sorted(KINDS):
            tick = 81 if kind == delayed else 4
            period = {'cpu_return': '0.4', 'dirty_writeback_callback': '1.25'}.get(kind, '1')
            gate.accept(kind, identity, expected[kind], tick, period)
        ready = {'cpu_return': 33, 'dirty_writeback_callback': 102}.get(delayed, 81)
        rejects(lambda: gate.release(ready - 1))
        rejects(lambda: gate.accept(delayed, identity, expected[delayed], 1, '1'))
        assert gate.release(ready) == ready
        checks += 6
print(json.dumps(dict(state='PASS_SYNTHETIC_GATE_ONLY', checks=checks,
                      runtime_paths_executed=0, cfg=['cond','uncond'])))
