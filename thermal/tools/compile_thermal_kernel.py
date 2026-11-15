"""Generate full-order modal RC response bounds from the packaged RC operator.

Extracted from analyze_whole_task_opp.operators and thermal_work_contracts
without their dense-Qwen workload dependencies. Original sources are recorded
in provenance. Regenerated coefficients are separate from frozen inputs.
"""
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
import numpy as np
from scipy.linalg import eigh
from scipy.sparse import eye
from scipy.sparse.linalg import splu
import portable
from op_thermal import ThermalPlant


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=portable.RUNS / 'preparation/thermal_kernel.json')
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(portable.INPUT):
        raise ValueError('Frozen packaged inputs cannot be overwritten.')
    portable.verify_inputs()
    op = portable.INPUT / 'prepared/operating_point_2ghz_rconv3'
    plant = ThermalPlant(45., op / 'rc')
    n = len(plant.state)
    solve = splu(eye(n, format='csc') - .0005 * plant.A).solve
    transition = solve(solve(np.eye(n)))
    scale = np.sqrt(transition[0] / transition[:, 0])
    symmetric = scale[:, None] * transition / scale[None, :]
    assert np.max(abs(symmetric - symmetric.T)) < 1e-9
    poles, q = eigh((symmetric + symmetric.T) / 2, check_finite=False, driver='evd')
    assert 0 < poles.min() <= poles.max() < 1
    inverse = q / scale[:, None]
    half = solve((.0005 * plant.B).toarray())
    inputs = (q.T * scale[None, :]) @ (half + solve(half))
    output = np.asarray(plant.C @ inverse)
    transform = inverse.T / np.sum(inverse * inverse, axis=1)[None, :]
    assert np.max(abs(transform @ inverse - np.eye(n))) < 1e-9
    scenario = json.loads((op / 'scenario.json').read_text())
    curves = json.loads((portable.RUNTIME / 'prepared/memory_curves.json').read_text())
    p = scenario['power']
    idle = np.zeros(96)
    idle[:16] = p['core_static_W'] + p['lbuf_leak_W'] + p['router_static_W'] + p['ni_static_W']
    idle[16:32] = p['sram_leak_W']
    idle[32:] = curves['1']['idle_W_per_partition'] / 4
    idle_modes = inputs @ idle / (1 - poles)
    edges = np.array([0, 1, 2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256,
        384, 512, 768, 1024, 1536, 2048, 3072, 4096, 8192, 16384, 32768, 65536, np.inf])
    left = np.exp(np.outer(np.log(poles), edges[:-1]))
    right = np.zeros_like(left)
    right[:, :-1] = np.exp(np.outer(np.log(poles), edges[1:-1]))
    maximum = np.empty((96, 96))
    for source in range(96):
        terms = output * (inputs[:, source] / .001)[None, :]
        maximum[:, source] = np.maximum(np.max(np.maximum(terms, 0.) @ left +
            np.minimum(terms, 0.) @ right, axis=1), 0.) + 1e-8
    modes = np.zeros(n)
    power = idle.copy()
    power[3] += 1.
    replay_error = 0.
    for _ in range(256):
        modes = poles * modes + inputs @ power
        actual = plant.step(power)
        replay_error = max(replay_error, float(np.max(abs(actual - 45. - output @ modes))))
    assert replay_error < 1e-7
    values = dict(poles=poles, U=inputs, output=output, inverse_transform=transform,
        idle_power=idle, idle_modes=idle_modes, idle_temperature=45. + output @ idle_modes,
        edges=edges, impulse_upper_K_per_J=maximum)
    payload = {k: v.tolist() for k, v in values.items()}
    payload['edges'][-1] = 'Infinity'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, separators=(',', ':'), allow_nan=False) + '\n')
    print('PASS_FULL_ORDER_RC_KERNEL', n, 'states; replay_error_C', replay_error, args.output)


if __name__ == '__main__':
    main()
