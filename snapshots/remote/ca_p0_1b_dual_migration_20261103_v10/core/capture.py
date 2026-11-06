"""Validate captured-trace identity; never opens a model or generates routes."""
from .common import require
from .scheduling import validate_split


def validate_capture(metadata, records, requested_model, representation=None):
    require(metadata.get("model_id") == requested_model, "captured model differs from requested model")
    representation = representation or {"variant": "original", "weight_dtype": "BF16"}
    require(metadata.get("variant") == representation["variant"] and not metadata.get("quantization"),
            "runtime representation differs from the explicit model contract")
    require(metadata.get("weight_dtype") == representation["weight_dtype"], "capture dtype differs")
    if representation["variant"] == "gptq_decoded_fp16":
        require(metadata.get("source_quantization") == "GPTQ_INT4" and
                metadata.get("decoded_manifest_sha256"), "decoded FP16 provenance required")
    for field in ("checkpoint_content_sha256", "tokenizer_sha256"):
        require(metadata.get(field), "capture identity missing:" + field)
    require(metadata.get("revision") or metadata.get("content_snapshot_id"), "immutable capture snapshot required")
    require(metadata.get("traffic_mode") in ("teacher_forced", "generated"), "traffic mode required")
    require(metadata.get("phase") in ("prefill", "decode"), "capture phase required")
    require(metadata.get("is_performance_measurement") is False,
            "router trace collection is not serving timing")
    return {"split": validate_split(records), "identity": metadata,
            "model_loaded_here": False, "timing_claim": False}
