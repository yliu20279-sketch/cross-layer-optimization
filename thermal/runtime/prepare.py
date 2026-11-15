"""I/O compatibility for the frozen native runtime; no workload construction."""
import csv
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
PREP = ROOT / 'prepared'
def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
def writecsv(path, data):
    if not data:
        return
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)
