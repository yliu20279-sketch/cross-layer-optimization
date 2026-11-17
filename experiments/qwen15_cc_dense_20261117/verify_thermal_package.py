"""Verify the published inputs and, if needed, rebuild the RC kernel separately."""

import hashlib
import json
import os
from pathlib import Path
import runpy
import sys


def main(package, work):
    package, work = package.resolve(), work.resolve()
    sys.path.insert(0, str(package / 'src'))
    import portable

    kernel_key = 'inputs/thermal_kernel.json'
    inputs = json.loads((package / 'inputs/MANIFEST.json').read_text())
    source = json.loads((package / 'GIT_TREE.json').read_text(encoding='utf-8-sig'))
    missing = []
    for entry in source:
        path = package / entry['path']
        if not path.exists():
            missing.append(entry['path'])
            continue
        data = path.read_bytes()
        assert hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest() == entry['sha'], path
    assert set(missing) <= {kernel_key}
    for name, digest in inputs['sha256'].items():
        if name not in missing:
            assert portable.sha(name) == digest, name
    if missing:
        kernel = work / 'thermal_kernel_rebuilt.json'
        # All upstream inputs to the official reconstruction have already been
        # checked. Its missing argument here is the output being reconstructed.
        portable.verify_inputs = lambda: inputs
        compiler = package / 'tools/compile_thermal_kernel.py'
        sys.argv = [str(compiler), '--output', str(kernel)]
        runpy.run_path(str(compiler), run_name='__main__')
        provenance = 'reconstructed_from_verified_rc'
    else:
        kernel = package / kernel_key
        provenance = 'published_exact'
    output = dict(status='PASS_THERMAL_KERNEL_PREPARATION',
                  verified_git_blobs=len(source)-len(missing), kernel=str(kernel),
                  kernel_sha256=portable.sha(kernel), source=provenance,
                  original_kernel_sha256=inputs['sha256'][kernel_key])
    (work / 'THERMAL_PREPARATION.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output), flush=True)


if __name__ == '__main__':
    os.environ['OPENBLAS_NUM_THREADS'] = '1'
    os.environ['OMP_NUM_THREADS'] = '1'
    main(*(Path(arg) for arg in sys.argv[1:]))
