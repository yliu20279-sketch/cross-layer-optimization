#!/usr/bin/env python3
"""Collect deterministic top-k Qwen2-MoE routes from ShareGPT conversations.

The first 512 tokens are labelled prefill and the next 128 teacher-forced
tokens are labelled decode. Padding positions are never written.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import random
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def load_conversations(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        obj = json.load(handle)
    if isinstance(obj, dict):
        for key in ("data", "train", "conversations"):
            if key in obj and isinstance(obj[key], list):
                obj = obj[key]
                break
    if not isinstance(obj, list):
        raise ValueError("ShareGPT input must be a JSON list")
    return obj


def messages_of(record: dict) -> list[dict[str, str]]:
    turns = record.get("conversations") or record.get("messages") or []
    messages = []
    role_map = {"human": "user", "user": "user", "gpt": "assistant", "assistant": "assistant",
                "system": "system"}
    for turn in turns:
        role = role_map.get(str(turn.get("from", turn.get("role", ""))).lower())
        text = turn.get("value", turn.get("content", ""))
        if role and isinstance(text, str) and text.strip():
            messages.append({"role": role, "content": text.strip()})
    return messages


def stable_id(record: dict, index: int) -> str:
    raw = str(record.get("id") or record.get("conversation_id") or f"row-{index}")
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--sharegpt", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--requests", type=int, default=100)
    ap.add_argument("--profile-fraction", type=float, default=0.2)
    ap.add_argument("--prompt-tokens", type=int, default=512)
    ap.add_argument("--decode-tokens", type=int, default=128)
    ap.add_argument("--seed", type=int, default=20260912)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    records = load_conversations(args.sharegpt)
    usable = [(i, r, messages_of(r)) for i, r in enumerate(records)]
    usable = [(i, r, m) for i, r, m in usable if len(m) >= 2]
    rng = random.Random(args.seed)
    rng.shuffle(usable)
    if len(usable) < args.requests:
        raise ValueError(f"only {len(usable)} usable conversations for {args.requests} requests")
    total_tokens = args.prompt_tokens + args.decode_tokens

    # Enforce the requested 512+128 workload shape using real, non-padding
    # tokens. Selection remains deterministic because candidates are shuffled
    # once with the recorded seed and accepted in that order.
    selected = []
    for source_index, record, messages in usable:
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        encoded = tokenizer(
            text, return_tensors="pt", truncation=True, max_length=total_tokens,
            padding=False, add_special_tokens=False,
        )
        if encoded.input_ids.shape[1] >= total_tokens:
            selected.append((source_index, record, messages, text, encoded))
            if len(selected) == args.requests:
                break
    if len(selected) < args.requests:
        raise ValueError(f"only {len(selected)} conversations contain at least {total_tokens} tokens")
    n_profile = round(args.requests * args.profile_fraction)

    model = AutoModelForCausalLM.from_pretrained(
        args.model, device_map={"": 0}, torch_dtype="auto", local_files_only=True
    )
    model.config.output_router_logits = True
    model.eval()

    trace_path = args.out / "routing_trace.csv.gz"
    manifest_rows = []
    with gzip.open(trace_path, "wt", newline="", encoding="utf-8") as handle:
        fields = ["request_id", "split", "position", "phase", "token_id", "layer",
                  "expert", "route_prob", "count"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for sample_index, (source_index, record, messages, text, encoded) in enumerate(selected):
            request_id = stable_id(record, source_index)
            split = "profile" if sample_index < n_profile else "eval"
            valid = int(encoded.attention_mask.sum())
            if valid != total_tokens:
                raise RuntimeError(f"selection invariant failed: {valid} != {total_tokens}")
            inputs = {k: v.to("cuda") for k, v in encoded.items()}
            with torch.inference_mode():
                outputs = model(**inputs, output_router_logits=True, use_cache=False, return_dict=True)
            if len(outputs.router_logits) != 24:
                raise RuntimeError(f"expected 24 router layers, got {len(outputs.router_logits)}")
            token_ids = encoded.input_ids[0, :valid].tolist()
            for layer, logits in enumerate(outputs.router_logits):
                logits = logits.reshape(1, total_tokens, -1)[0, :valid].float()
                probs = torch.softmax(logits, dim=-1)
                top_prob, top_expert = torch.topk(probs, k=4, dim=-1)
                for position, token_id in enumerate(token_ids):
                    phase = "prefill" if position < args.prompt_tokens else "decode_teacher_forced"
                    for expert, probability in zip(top_expert[position].tolist(), top_prob[position].tolist()):
                        writer.writerow({
                            "request_id": request_id, "split": split, "position": position,
                            "phase": phase, "token_id": token_id, "layer": layer,
                            "expert": expert, "route_prob": f"{probability:.9g}", "count": 1,
                        })
            manifest_rows.append({
                "request_id": request_id, "split": split, "source_index": source_index,
                "valid_tokens": valid, "messages": len(messages),
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            })
            print(json.dumps({"completed": sample_index + 1, "requests": args.requests,
                              "request_id": request_id, "valid_tokens": valid}), flush=True)

    manifest = {
        "schema_version": "qwen-router-trace-1.0",
        "model": str(args.model),
        "dataset_file": str(args.sharegpt),
        "dataset_sha256": hashlib.sha256(args.sharegpt.read_bytes()).hexdigest(),
        "selection_seed": args.seed,
        "requests": args.requests,
        "profile_requests": n_profile,
        "eval_requests": args.requests - n_profile,
        "prompt_tokens": args.prompt_tokens,
        "decode_tokens": args.decode_tokens,
        "decode_method": "teacher_forced_from_sharegpt_conversation",
        "top_k": 4,
        "records": manifest_rows,
        "limitations": [
            "The decode segment is teacher-forced, not autoregressively generated by Qwen.",
            "Results characterize the fixed sampled requests, not the full ShareGPT population.",
        ],
    }
    (args.out / "trace_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
