import pathlib,json,hashlib
p=pathlib.Path(__file__).resolve().parent
s=(p/'run_fragment.py').read_text().replace("D=R/'attempt1'","D=R/'attempt2'").replace("R/'PRE_RUN_FREEZE.json'","R/'PRE_RUN_FREEZE_v2.json'").replace("R/'run_fragment.py'","R/'run_fragment_v2.py'")
assert not (p/'run_fragment_v2.py').exists()
(p/'run_fragment_v2.py').write_text(s)
(p/'PRE_RUN_FREEZE_v2.json').write_text(json.dumps({n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in ['run_fragment_v2.py','PROTOCOL.json']},indent=2))
(p/'STARTUP_FAILURE.json').write_text(json.dumps(dict(attempt='attempt1',interpreter='swe_qwen3_step3_gpu_20261026_v1/venv/bin/python',error='ModuleNotFoundError: No module named onnx',stage='base runtime import; before native initialization or model request',resolution='reuse original native runtime environment in new attempt2; no environment installation or arithmetic change'),indent=2))
