"""Packaged MoE inputs and full-state warm checkpoints.
The original pilot source is identified in provenance/SOURCE_MANIFEST.json.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import csv
import json
import math
from pathlib import Path
import numpy as np
from portable import PACKAGE, SRC, INPUT, RUNS, sha, verify_inputs, warm_record
HERE = SRC
OUT = RUNS / 'pilot'
ORIGINAL_PREP = INPUT / 'prepared'
LOCAL_PREP = ORIGINAL_PREP
LOCAL_OP = LOCAL_PREP / 'operating_point_2ghz_rconv3'
def prepare():
    verify_inputs()
    import graph_scheduler as scheduler
    import amber_online_qwen as amber
    scheduler.PREP = LOCAL_PREP
    amber.PREP = LOCAL_PREP
    return scheduler, amber
def warm_state(scheduler, requests):
    record = warm_record(requests)
    assert record['profile_sha256'] == sha(LOCAL_OP / 'gtp_srs_native_opp_profiles.json')
    return np.asarray(record['state'], dtype=float)


def validate(sim):
    """Check complete work, native services, DAG and Array/partition calendars."""
    assert len(sim.task_rows) == sim.requests * len(sim.tasks)
    assert sum(row["MAC"] for row in sim.task_rows) == sim.requests * sim.mac_per_request
    rows = {(row["request"], row["task_id"]): row for row in sim.task_rows}
    arrays = [[] for _ in range(16)]
    partitions = [[] for _ in range(16)]
    duration_error = 0.
    for key, row in rows.items():
        task = sim.tasks[key[1]]
        profile = sim.profile(task, row["opp_ratio"])
        compute_end = row["start_ns"] + profile["duration_ns"]
        assert row["end_ns"] + 1e-4 >= compute_end
        duration_error = max(duration_error, max(0., compute_end - row["end_ns"]))
        assert all(rows[key[0], dep]["end_ns"] <= row["start_ns"] + 1e-4
                   for dep in task["deps"])
        assert row["MAC"] == task["mac_ops"]
        arrays[row["cluster"]].append((row["start_ns"], compute_end))
        partitions[row["memory_partition"]].append((row["start_ns"], row["end_ns"]))
    for intervals in arrays + partitions:
        ordered = sorted(intervals)
        assert all(left[1] <= right[0] + 1e-4
                   for left, right in zip(ordered, ordered[1:]))
    return dict(status="COMPLETE_WORK_DAG_NATIVE_SERVICE_RESOURCE_PASS",
                tasks=len(rows), MAC=sim.requests * sim.mac_per_request,
                native_service_underrun_ns=duration_error)
