from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
suite=unittest.defaultTestLoader.discover(str(ROOT/'validation'),pattern='test_*.py')
result=unittest.TextTestRunner(verbosity=2).run(suite)
receipt={'status':'PASS_SOFTWARE_AND_DECODE_REFERENCE_ONLY' if result.wasSuccessful() else 'FAIL',
         'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
         'native_simulations':0,'model_forwards':0,'gpu_runs':0,'p0_2_started':False}
path=ROOT/'evidence/SOFTWARE_CHECKS_v3.json'
if path.exists():
    count=1
    while path.with_name('SOFTWARE_CHECKS_v3_attempt%d.json'%count).exists():count+=1
    path.rename(path.with_name('SOFTWARE_CHECKS_v3_attempt%d.json'%count))
path.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
raise SystemExit(0 if result.wasSuccessful() else 1)
