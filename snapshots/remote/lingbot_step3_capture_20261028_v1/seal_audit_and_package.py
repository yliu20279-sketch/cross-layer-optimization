import pathlib,json,time,subprocess,sys
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step3_capture_20261028_v1')
a=json.loads((P/'INDEPENDENT_CAPTURE_AUDIT.json').read_text())
assert a['status']=='PASS_LIMITED_REAL_ROUTE_CAPTURE_AND_FIXTURE_INTEGRITY' and not a['failures']
last=(P/'audit_attempt3.log').read_text().splitlines()[-1]
assert json.loads(last)['status']==a['status']
(P/'AUDIT_EXIT.json').write_text(json.dumps(dict(exit_code=0,time=time.time(),audit_script='audit_capture_attempt3.py',basis='successful final report and final stdout marker',first_failure_preserved='AUDIT_EXIT_attempt1.json')))
with (P/'package.log').open('w') as f:
    result=subprocess.run([sys.executable,str(P/'package_evidence.py')],stdout=f,stderr=subprocess.STDOUT)
(P/'PACKAGE_EXIT.json').write_text(json.dumps(dict(exit_code=result.returncode,time=time.time())))
sys.exit(result.returncode)
