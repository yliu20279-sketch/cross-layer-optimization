"""V3.5 physical 8x8 DRAM blocks aligned to 4x4 Logic regions."""
import hashlib
from pathlib import Path

import numpy as np


def dram_to_logic_regions(dram_temperature):
    """Take the hottest DRAM block in each aligned 2x2 physical square.

    The last axis is DRAM0..DRAM63 in row-major floorplan order. Earlier
    axes, if present, are preserved (e.g. a time series of temperature maps).
    """
    values = np.asarray(dram_temperature)
    if values.ndim < 1 or values.shape[-1] != 64:
        raise ValueError("Expected last axis to contain 64 DRAM blocks")
    grouped = values.reshape(values.shape[:-1] + (4, 2, 4, 2))
    return grouped.max(axis=(-3, -1)).reshape(values.shape[:-1] + (16,))


def validate_offline_geometry(record):
    """Reject cached mappings scored before the physical alignment fix."""
    expected = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if (record.get("physical_DRAM_2x2_grouping") is not True or
            record.get("source_geometry_sha256") != expected):
        raise RuntimeError("AMBER offline mapping lacks current physical 2x2 "
                           "DRAM alignment provenance; rerun amber_offline_qwen.py "
                           "at the selected operating point before using it")
