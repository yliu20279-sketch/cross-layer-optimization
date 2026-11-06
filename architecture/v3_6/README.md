# Target Architecture V3.6

V3.6 is a non-destructive capacity fork of V3.5 for the Qwen3-8B W4A16 mapping study. V3.5 remains unchanged.

The only intended hardware change is HB-DRAM capacity:

- total capacity: 4096 MiB to 8192 MiB;
- partitions: unchanged at 16;
- capacity per partition: 256 MiB to 512 MiB;
- Ramulator2 row depth: 8192 to 16384;
- logical projected banks: unchanged at four per partition;
- decoded Ramulator2 banks: unchanged at sixteen per partition;
- HB bandwidth: unchanged at 25.6 GB/s per NPU-DRAM pair;
- horizontal NoC and NPU parameters: unchanged.

The partition selector changes from `address[31:28]` to `address[32:29]`, because each partition now spans 2^29 bytes and the complete address space spans 2^33 bytes.

V3.6 is configuration-ready but has not passed execution validation. V3.5 validation results are retained only as provenance and must not be presented as V3.6 results. Absolute thermal execution remains blocked by the same unresolved Hybrid-Bonding geometry and interface-RC fields as V3.5.

Run the deterministic materializer and self-check with the bundled Python environment:

```text
python build_v3_6.py
python check_v3_6.py
```

The Qwen capacity profile uses the exact 8,190,427,136 parameters represented by the generated operator graph. The positive theoretical W4A16 headroom does not prove deployability: serialized scale and zero-point metadata, per-partition imbalance, activation buffers and collective workspaces must still be measured.
