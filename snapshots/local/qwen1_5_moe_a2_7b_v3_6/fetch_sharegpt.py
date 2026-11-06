#!/usr/bin/env python3
"""Resolve and download a pinned ShareGPT source file."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="anon8231489123/ShareGPT_Vicuna_unfiltered")
    ap.add_argument("--filename")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--endpoint", default="https://hf-mirror.com")
    args = ap.parse_args()
    api = HfApi(endpoint=args.endpoint)
    info = api.dataset_info(args.repo)
    files = api.list_repo_files(args.repo, repo_type="dataset", revision=info.sha)
    if not args.filename:
        print(json.dumps({"repo": args.repo, "revision": info.sha, "files": files}, indent=2))
        return
    args.out.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(
        args.repo, args.filename, repo_type="dataset", revision=info.sha,
        local_dir=args.out, endpoint=args.endpoint,
    )
    print(json.dumps({"repo": args.repo, "revision": info.sha, "filename": args.filename,
                      "path": path}, indent=2))


if __name__ == "__main__":
    main()
