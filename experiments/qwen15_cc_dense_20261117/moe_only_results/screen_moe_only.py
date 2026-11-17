"""Screen reactive circuits for the serialized 4 KiB MoE transfers without GetS."""

import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from planner import wired_paths


def test_transfer(base, binary, folder, source, destination, image):
    folder.mkdir()
    release = 32
    (folder/'unified.stim').write_text(f'0 0 0 {source} {destination} {release}\n')
    (folder/'plan.stim').write_text(f'0 {image:x}\n' + ('0\n' if image else ''))
    options = dict(mode=2 if image else 0, bank=4, ctrl=32, install=8, priority=1, depth=4,
                   cc=0, decision=release, packets=1, indep=0, mesh_only=int(not image))
    command = ['docker','run','--rm','--network','none','--read-only','--user',f'{os.getuid()}:{os.getgid()}',
               '-v',f'{base}:/work','-w',f'/work/{folder.relative_to(base)}',
               '--entrypoint',f'/work/{binary.relative_to(base)}','ub-pim:24.04']
    command.extend(f'+{key}={value}' for key,value in options.items())
    (folder/'command.json').write_text(json.dumps(command)+'\n')
    with (folder/'rtl.log').open('w') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=90)
    with (folder/'rtl.log').open() as log:
        rows = list(csv.reader(log))
    done, = [r for r in rows if r and r[0]=='DONE']
    bind, = [r for r in rows if r and r[0]=='BIND']
    assert tuple(map(int,done[1:3])) == (0,0)
    assert tuple(map(int,bind[1:3])) == (0,0) and int(bind[4]) == bool(image)
    assert int(done[4]) == release
    installs = [int(r[1]) for r in rows if r and r[0]=='INSTALL_READY']
    if image:
        install, = installs
        assert install >= release+40 and int(bind[3]) >= install
    else:
        assert not installs
    return dict(cycles=int(done[5])-release, bind_cycles=int(bind[3])-release, install_ticks=installs)


def main(contract, previous, out):
    frozen = contract.read_bytes()
    work = json.loads(frozen)['transport']
    assert len(work)==15 and all(row['bytes']==4096 for row in work)
    routes = wired_paths()
    base = previous.parent
    binary = previous/'obj/Vunified_tb'
    out.mkdir()
    pairs = []
    for source,destination in sorted({(row['src'],row['dst']) for row in work}):
        tag = f'{source}-{destination}'
        mesh = test_transfer(base,binary,out/f'{tag}-mesh',source,destination,0)
        trials = []
        for i,route in enumerate(routes.get((source,destination),[])):
            measured = test_transfer(base,binary,out/f'{tag}-cs{i}',source,destination,route.image)
            gain = mesh['cycles']-measured['cycles']
            trials.append(dict(**measured, image=f'{route.image:x}', switches=route.switches,
                               gain_cycles=gain, guard_pass=gain>1))
        selected = max((t for t in trials if t['guard_pass']),key=lambda t:t['gain_cycles'],default=None)
        pairs.append(dict(src=source,dst=destination,mesh=mesh,trials=trials,selected=selected,
                          messages=sum((e['src'],e['dst'])==(source,destination) for e in work)))
    result = dict(status='PASS_MOE_ONLY_REACTIVE_RTL_SCREEN', contract_sha256=hashlib.sha256(frozen).hexdigest(),
                  rtl_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(), gets=0,
                  scope='Single eligible 4 KiB message per decision; common RTL logical Bank and NI. '
                        '32-cycle control plus 8-cycle activation; no preinstalled circuits or cross-message amortization.',
                  selected='reactive_cs' if any(p['selected'] for p in pairs) else 'mesh', pairs=pairs)
    (out/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':
    main(*(Path(arg).resolve() for arg in sys.argv[1:]))
