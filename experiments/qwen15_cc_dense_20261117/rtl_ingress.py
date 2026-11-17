"""Exercise the actual CS/Bank RTL with the frozen GetS and first MoE dispatch."""

import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from planner import wired_paths


def load(path):
    return json.loads(path.read_text())


def patch_rtl():
    source = Path('experiment_tb.sv').read_text()
    replacements = {
        'len[i]=132;': 'len[i]=128;',
        'len[i]=id[i]<cc_count ? 1 : 3;': 'len[i]=id[i]<cc_count ? 1 : 2;',
        'app_count*132 : 0)+4*cc_count': 'app_count*128 : 0)+3*cc_count',
    }
    for original, replacement in replacements.items():
        assert source.count(original) == 1, original
        source = source.replace(original, replacement)
    Path('ingress_tb.sv').write_text(source)


def run(case, arrivals_path, destination, image, assignments):
    arrivals = load(arrivals_path)
    txns = arrivals['transactions']
    count = len(txns)
    period = txns[1]['arrival'] - txns[0]['arrival']
    assert [r['arrival'] for r in txns] == list(range(0, 512, period))
    assert [(r['src'], r['dst'], r['request_bytes'], r['read_bytes'], r['reply_bytes'])
            for r in txns] == [(0, 1, 32, 64, 64)] * count
    start = arrivals['nominal_overlap_cycles'][0]
    destination.mkdir(parents=True)
    (destination / 'unified.stim').write_text(f'0 0 0 0 1 {start}\n')
    (destination / 'plan.stim').write_text(f'0 {image:x}\n' + ''.join(f'{i}\n' for i in assignments))
    options = dict(mode=2 if image else 0, bank=4, ctrl=32, install=8, priority=1, depth=4,
                   cc=count, ccstart=0, ccperiod=period, ccsrc=0, ccdst=1,
                   decision=start, packets=1, indep=0, mesh_only=int(not image))
    cmd = ['docker', 'run', '--rm', '--network', 'none', '--read-only', '--user',
           f'{os.getuid()}:{os.getgid()}', '-v', f'{Path.cwd()}:/work',
           '-w', f'/work/{destination}', '--entrypoint', '/work/obj/Vunified_tb', 'ub-pim:24.04']
    cmd += [f'+{key}={value}' for key, value in options.items()]
    (destination / 'command.json').write_text(json.dumps(cmd))
    with (destination / 'rtl.log').open('w') as raw:
        subprocess.run(cmd, check=True, stdout=raw, stderr=subprocess.STDOUT, timeout=90)
    with (destination / 'rtl.log').open() as raw:
        rows = list(csv.reader(raw))
    messages = {(int(r[1]), int(r[2])): tuple(map(int, r[4:])) for r in rows if r and r[0] == 'DONE'}
    binds = {(int(r[1]), int(r[2])): tuple(map(int, r[3:])) for r in rows if r and r[0] == 'BIND'}
    assert len(messages) == len(binds) == 1 + 2 * count
    for i, txn in enumerate(txns):
        assert messages[2, i][0] == txn['arrival']
        assert messages[2, i][1] == messages[2, count+i][0]
        assert binds[2, count+i][0] >= messages[2, i][1]
    tail = max(messages[2, count+i][1] for i in range(count))
    moe = messages[0, 0][1]
    installs = [int(r[1]) for r in rows if r and r[0] == 'INSTALL_READY']
    if image:
        install, = installs
        committed, = [r for r in rows if r and r[0] == 'COMMIT']
        assert int(committed[2], 16) == image and install == int(committed[1]) + 8 >= start + 40
        for idx in assignments:
            tick, plane = binds[0, 0] if idx == 0 else binds[2, idx-1]
            assert tick >= install and plane == 1
    else:
        assert not installs and all(v[1] == 0 for v in binds.values())
    edges = sum(1 for r in rows if r[:3] == ['EDGE', '0', '1'])
    return dict(case=case, cc=tail, first_dispatch_bank_done=moe, join=max(moe, tail),
                switched=bool(image), mesh_0_to_1_grants=edges, assigned_frames=len(assignments),
                install_ticks=installs), binds


def main():
    route, = wired_paths()[0, 1]
    result = []
    for name in ('combined_overload', 'matched'):
        inputs = Path('..') / f'{name}.json'
        ref = load(Path('..') / name / 'LAUNCH.json')
        assert hashlib.sha256(inputs.read_bytes()).hexdigest() == ref['arrivals_sha256']
        base, binds = run(name, inputs, Path(name) / 'mesh', 0, [])
        at = load(inputs)['nominal_overlap_cycles'][0]
        eligible = [i + 1 for (app, i), (tick, _) in binds.items()
                    if app == 2 and i < len(load(inputs)['transactions']) and tick >= at]
        trials = [base]
        for label, indices in (('moe', [0]), ('gets', eligible), ('joint', [0] + eligible)):
            alternative, trial_binds = run(name, inputs, Path(name) / label, route.image, indices)
            assert {k: v for k, v in binds.items() if v[0] < at} == {
                k: v for k, v in trial_binds.items() if v[0] < at}
            alternative['arm'] = label
            alternative['guard_pass'] = (alternative['cc'] <= base['cc'] and
                alternative['first_dispatch_bank_done'] <= base['first_dispatch_bank_done'] and
                base['join'] - alternative['join'] > 1)
            trials.append(alternative)
        selected = min((t for t in trials if t.get('guard_pass')), key=lambda t: t['join'], default=base)
        result.append(dict(case=name, trials=trials, selected=selected.get('arm', 'mesh')))
    receipt = dict(status='PASS_RTL_FIRST_DISPATCH_INGRESS_ONLY',
                   scope='RTL Bank and link timing model; no DRAM, full layer or thermal feedback', cases=result)
    Path('RTL_INGRESS.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    if sys.argv[1] == 'prepare':
        patch_rtl()
    else:
        main()
