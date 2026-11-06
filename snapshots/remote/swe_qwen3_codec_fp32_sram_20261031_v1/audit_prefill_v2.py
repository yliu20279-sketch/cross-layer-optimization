from pathlib import Path
import subprocess
OLD=Path(__file__).resolve().parent;R=OLD.parent/'swe_qwen3_codec_prefill_sram_20261031_v2'
s=(OLD/'audit.py').read_text()
s=s.replace("assert hashlib.sha256(x.tobytes()).hexdigest()==v['input_sha256']", "protocol=j(R/'PROTOCOL.json');ref=Path(protocol['input_source']);assert sha(ref)==protocol['input_source_sha256'];assert x.tobytes()==np.fromfile(ref,dtype='<u2').reshape(19,2048)[protocol['tokens']].tobytes()")
s=s.replace("reference=np.empty(768,dtype='<f4')","reference=np.empty(4608,dtype='<f4')").replace('reference.ctypes.data,1,768,2048','reference.ctypes.data,6,768,2048')
s=s.replace('1574912','1585152').replace("cpu['encoded_elements']==768","cpu['encoded_elements']==4608")
s=s.replace('(1572864,1573632,48384,202752,12)','(9437184,9446400,0,1180224,12)').replace("low['compute_cycles']==202752","low['compute_cycles']==1180224")
s=s.replace('len(rows)==768','len(rows)==288').replace("int(v['row'])==i and int(v['weight_version'])==i//64+1", "int(v['row'])==((i//24)*64+((i%24)//4)*768+(i%4)*16) and int(v['weight_version'])==i//24+1")
s=s.replace('strict_FP32_elements=768,strict_BF16_elements=768','strict_FP32_elements=4608,strict_BF16_elements=4608').replace('CPU_encode_elements=768','CPU_encode_elements=4608').replace('PASS_LIMITED_ACTUAL_CPU_CODEC_FP32_GATE_SRAM_TWO_ROUND','PASS_LIMITED_REAL_PREFILL_M6_CPU_CODEC_FP32_SRAM_TWO_ROUND')
(R/'audit.py').write_text(s)
PY=OLD.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
subprocess.run([str(PY),str(R/'audit.py')],check=True)
