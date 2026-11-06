#!/usr/bin/env python3
"""Load the local GPTQ checkpoint and verify Qwen2-MoE router outputs."""
from __future__ import annotations

import argparse
import json

import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    args = parser.parse_args()

    print(json.dumps({
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "cuda": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }))
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        device_map={"": 0},
        torch_dtype="auto",
        local_files_only=True,
    )
    model.config.output_router_logits = True
    inputs = tokenizer("Bank conflict routing smoke test.", return_tensors="pt").to("cuda")
    with torch.inference_mode():
        outputs = model(
            **inputs,
            output_router_logits=True,
            use_cache=False,
            return_dict=True,
        )
    router_logits = outputs.router_logits
    print(json.dumps({
        "input_shape": list(inputs.input_ids.shape),
        "layers": len(router_logits),
        "shapes": [list(t.shape) for t in router_logits[:2]],
        "experts": router_logits[0].shape[-1],
        "finite": bool(torch.isfinite(router_logits[0]).all()),
    }))


if __name__ == "__main__":
    main()
