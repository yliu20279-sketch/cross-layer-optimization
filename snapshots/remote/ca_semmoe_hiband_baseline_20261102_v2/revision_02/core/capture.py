"""Validate captured-trace identity; never opens a model or generates routes."""
from .common import require
from .scheduling import validate_split


def validate_capture(metadata, records, requested_model):
    require(metadata.get("model_id") == requested_model, "captured model differs from requested model")
    require(metadata.get("variant") == "original" and not metadata.get("quantization"),
            "Chat/GPTQ/quantized capture cannot substitute original")
    require(metadata.get("weight_dtype") == "BF16", "capture dtype differs")
    for field in ("checkpoint_content_sha256", "tokenizer_sha256", "revision"):
        require(metadata.get(field), "capture identity missing:" + field)
    require(metadata.get("traffic_mode") in ("teacher_forced", "generated"), "traffic mode required")
    require(metadata.get("phase") in ("prefill", "decode"), "capture phase required")
    require(metadata.get("is_performance_measurement") is False,
            "router trace collection is not serving timing")
    return {"split": validate_split(records), "identity": metadata,
            "model_loaded_here": False, "timing_claim": False}
