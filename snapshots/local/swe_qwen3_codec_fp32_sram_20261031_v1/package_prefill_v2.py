from pathlib import Path
import subprocess,shutil
OLD=Path(__file__).resolve().parent;R=OLD.parent/'swe_qwen3_codec_prefill_sram_20261031_v2'
shutil.copy2(OLD/'bank_challenge.cpp',R/'bank_challenge.cpp')
s=(OLD/'challenge_and_package.py').read_text().replace('PASS_LIMITED_ACTUAL_CPU_CODEC_FP32_GATE_SRAM_TWO_ROUND','PASS_LIMITED_REAL_PREFILL_M6_CPU_CODEC_FP32_SRAM_TWO_ROUND').replace('PASS_LIMITED_CODEC_FP32_SRAM_REVIEW_READY','PASS_LIMITED_REAL_PREFILL_M6_REVIEW_READY')
(R/'challenge_and_package.py').write_text(s)
subprocess.run(['/usr/bin/python3',str(R/'challenge_and_package.py')],check=True)
