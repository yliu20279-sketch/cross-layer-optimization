"""Recompute the local-energy OPP choice from the frozen native profiles."""
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
import portable
import run_moe60_mechanisms as experiment
from moe60_controller import Controller
from moe60_runtime import ExpertScheduler, banks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=portable.RUNS / 'preparation/energy_OPP_table.json')
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(portable.INPUT):
        raise ValueError('Frozen packaged inputs cannot be overwritten.')
    plan = experiment.compile_plan()
    scenario, config = experiment.configuration()
    controller = Controller(scenario, config, {}, 'amber', portable.warm_state(4))
    sim = ExpertScheduler(4, controller, plan, mechanism='none')
    table = {}
    for tid, task in sim.tasks.items():
        c = sim.memory_partition(task)
        domain = [c, 16 + c, *banks(c)]
        candidates = []
        for ratio in (1., .75, .5):
            profile = sim.profile(task, ratio)
            energy = controller._candidate_energy(sim, task, c, c, ratio)
            candidates.append(dict(OPP=ratio, duration_ns=profile['duration_ns'],
                local_J=float(energy.sum() + controller.static[domain].sum() * profile['duration_ns'] * 1e-9)))
        selected = min(candidates, key=lambda row: (row['local_J'], row['duration_ns'], -row['OPP']))
        assert selected['OPP'] == plan['choices'][str(tid)], tid
        table[tid] = dict(op=task['op'], chosen=selected['OPP'], candidates=candidates)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    experiment.dump(args.output, table)
    print('PASS_ALL_OPERATOR_CHOICES', len(table), 'task definitions', args.output)


if __name__ == '__main__':
    main()
