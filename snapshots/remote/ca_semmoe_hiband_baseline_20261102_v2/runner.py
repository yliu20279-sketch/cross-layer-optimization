"""Admission inspection only. No subprocess or simulator launch exists here."""
import argparse
import json
from pathlib import Path
from core.readiness import preflight


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("qwen3", "qwen15"), required=True)
    parser.add_argument("--check-only", action="store_true", required=True)
    args = parser.parse_args()
    path = Path(__file__).resolve().parent / "contracts" / (args.model + ".json")
    result = preflight(json.loads(path.read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
