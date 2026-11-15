"""Replay the supplied native compute plans and bounded DRAM profiles.

This does not invoke/rebuild NPUSim or Ramulator2; their frozen outputs are
inputs. Native operator execution and capacity-bounded SRAM policy are the
original implementation. The adapter supplies only portable GTPSRS inputs.
"""
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import argparse
import copy
import json
from pathlib import Path
import shutil
import sys

PACKAGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKAGE / 'src'))
sys.path.insert(0, str(PACKAGE / 'runtime'))
import portable
import backend
import build_native_profiles as native
import profile_operating_point as profiler


def model_init(self):
    self.sc = json.loads((portable.RUNTIME / 'modeled_scenario.json').read_text())
    self.sram_capacity_bytes = json.loads((native.PREP / 'native_hierarchy.json').read_text())['buffer_bytes']
    self.plans = json.loads((native.PREP / 'gtp_srs_native_plan.json').read_text())
    for plan in self.plans.values():
        shift = plan['pipeline_cycles']
        plan['waves'][0]['compute_cycles'] += shift
        for event in plan['waves'][0]['events']:
            event[0] += shift
            event[1] += shift
    self.memory = native.MoEMemory(self.sc)
    self.streamable = {}


def memory_init(self, scenario):
    curves = json.loads((portable.RUNTIME / 'prepared/memory_curves.json').read_text())
    initialization = copy.deepcopy(scenario)
    initialization['timing']['memory_backend'] = 'packaged_profiles_loaded_below'
    backend.Memory.__init__(self, initialization, curves)
    self.sc = scenario
    record = json.loads((native.PREP / 'gtp_srs_logical_wave_profiles.json').read_text())
    assert record['status'] == 'PASS' and 1 in record['completed_refresh_rates']
    self.wave_profiles = record['profiles']
    self.current_task = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=1, help='0 re-profiles all unique configurations; default1 is diagnostic.')
    parser.add_argument('--output-dir', type=Path, default=portable.RUNS / 'native_profile_replay')
    args = parser.parse_args()
    portable.verify_inputs()
    out = args.output_dir.resolve()
    if out.is_relative_to(portable.INPUT):
        raise ValueError('Frozen packaged inputs cannot be overwritten.')
    out.mkdir(parents=True, exist_ok=True)
    source = portable.INPUT / 'prepared/operating_point_2ghz_rconv3'
    shutil.copy2(source / 'scenario.json', out / 'scenario.json')
    shutil.copytree(source / 'rc', out / 'rc', dirs_exist_ok=True)
    native.PREP = profiler.PREP = portable.INPUT / 'prepared'
    native.PARENT = portable.RUNTIME
    native.ProfileModel.__init__ = model_init
    native.MoEMemory.__init__ = memory_init
    profiler.OP = out
    sys.argv = [str(Path(profiler.__file__)), '--policy', 'gtp_srs', '--limit', str(args.limit)]
    profiler.main()


if __name__ == '__main__':
    main()
