"""Re-execute a full warm cohort and check original schedule fingerprints.

This checks portability of the frozen diagnostic, not a new performance claim.
Generated task/flow/thermal traces stay in ignored local runs/ directories.
"""
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys
import time

PACKAGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKAGE / 'src'))
import numpy as np
import portable
import run_moe60_mechanisms as execution
from run_moe65_fixed12 import FastController
from moe60_runtime import ExpertScheduler, base
from op_thermal import ThermalPlant
from thermal_geometry import dram_to_logic_regions


def code_hashes():
    paths = list((PACKAGE / 'src').glob('*.py')) + list((PACKAGE / 'runtime').glob('*.py'))
    paths += list((PACKAGE / 'validation').glob('*.py')) + [Path(__file__).resolve()]
    return {str(p): portable.sha(p) for p in sorted(paths)}


def run(case):
    portable.verify_inputs()
    plan = execution.compile_plan()
    hashes = code_hashes()
    folder = portable.RUNS / 'portability_check' / case
    folder.mkdir(parents=True, exist_ok=True)
    summary_path = folder / 'summary.json'
    if summary_path.exists():
        result = json.loads(summary_path.read_text())
        assert result['code_hashes'] == hashes, 'Existing check used different source code; use a fresh THERMAL_RUN_DIR.'
        assert result['portability_status'] == 'PASS'
        print('ALREADY_VALIDATED', case, flush=True)
        return
    scenario, config = execution.configuration()
    initial = portable.warm_state(4)
    choices = {int(k): v for k, v in plan['choices'].items()}
    began = time.monotonic()

    def progress(ctl):
        print('PROGRESS', case, ctl.stage2['decisions'], 'tasks', ctl.current_bin * .001, 'simulated_s', flush=True)

    controller = FastController(scenario, config, choices, case, initial, progress)
    sim = ExpertScheduler(4, controller, plan, mechanism='none')
    end = sim.run()
    measured_end = math.ceil(end / 1e6) * 1e6
    controller.observe(sim)
    controller.advance(measured_end)
    power, components = base.render_trace(sim, measured_end)
    plant = ThermalPlant(45., execution.pilot.LOCAL_OP / 'rc')
    plant.state = initial.copy()
    temperature = np.asarray([plant.step(row) for row in power])
    assert np.max(abs(temperature[-1] - controller.temperature)) < 1e-8
    assert abs(power.sum() * .001 - components.sum()) < 1e-7
    validation = execution.runtime_validation(sim)
    result = dict(policy=case, case=case, cohort=1, requests=4, tasks=len(sim.task_rows),
        duration_s=measured_end * 1e-9, energy_J=float(components.sum()), peak_C=float(temperature.max()),
        D60_K2_s=float((np.maximum(temperature[:, :16] - 60., 0.) *
            np.maximum(dram_to_logic_regions(temperature[:, 32:]) - 60., 0.)).sum() * .001),
        NoC_bytes=sum(flow['bytes'] for flow in sim.net.flows), copy_count=0, copy_bytes=0,
        moved_expert_invocations=0, source_hashes=plan['source_hashes'], code_hashes=hashes,
        controller=controller.report(), validation=validation, host_seconds=time.monotonic() - began)
    expected = json.loads((portable.reference_case(case) / 'summary.json').read_text())
    for name in ['duration_s', 'energy_J', 'peak_C', 'D60_K2_s']:
        assert abs(result[name] - expected[name]) < 1e-8, (name, result[name], expected[name])
    assert result['NoC_bytes'] == expected['NoC_bytes']
    execution.write_csv(folder / 'tasks.csv', sim.task_rows)
    execution.write_csv(folder / 'flows.csv', sim.net.flows)
    execution.dump(folder / 'expert_buffers.json', [dict(request=k[0], phase=k[1], layer=k[2], expert=k[3], **v)
                    for k, v in sim.slots.items()])
    portable.assert_first_schedule(folder, case)
    np.savez_compressed(folder / 'trace.npz', initial_state=initial, end_state=plant.state,
                        power_W=power, temperature_C=temperature, components_J=components)
    result['portability_status'] = 'PASS'
    result['original_task_and_flow_csv_fingerprints_match'] = True
    execution.dump(summary_path, result)

    spec = importlib.util.spec_from_file_location('portable_audit', portable.VALIDATION / 'audit_sustained.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    native = audit.read(audit.common.OP / 'gtp_srs_native_opp_profiles.json')
    tasks = {t['task_id']: t for t in audit.read(audit.common.PREP / 'gtp_srs_manifest.json')['tasks']}
    check, _ = audit.cohort_check(folder, initial, {}, native, tasks, scenario, plan)
    assert code_hashes() == hashes
    execution.dump(folder / 'independent_audit.json', check)
    print('PASS_MATCHED_FIRST_COHORT', json.dumps({k: result[k] for k in
          ['case', 'tasks', 'duration_s', 'energy_J', 'peak_C', 'D60_K2_s']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=['amber_energy', 'contract_energy'], required=True)
    run(parser.parse_args().case)
