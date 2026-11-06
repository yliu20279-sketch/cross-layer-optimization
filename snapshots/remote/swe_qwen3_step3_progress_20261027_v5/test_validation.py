from validation import validate_submission,feedback,test_selection,SYNTAX_SCRIPT
import subprocess,sys,json,hashlib
from pathlib import Path
class Env:
    def __init__(self,results):self.results=iter(results);self.commands=[]
    def execute(self,action):self.commands.append(action['command']);return next(self.results)
bad=Env([dict(returncode=1,output='IndentationError: expected an indented block')])
passed,report=validate_submission(bad,['src/pkg/a.py'])
assert not passed and len(bad.commands)==1 and report['tests'] is None and 'IndentationError' in feedback(report)
fail=Env([dict(returncode=0,output='syntax ok'),dict(returncode=1,output='FAILED test_original')])
passed,report=validate_submission(fail,['src/pkg/a.py'],default_full_suite=True);assert not passed and 'test_original' in feedback(report)
good=Env([dict(returncode=0,output='syntax ok'),dict(returncode=0,output='10 passed')])
passed,report=validate_submission(good,['src/pkg/a.py'],default_full_suite=True);assert passed and len(good.commands)==2
assert report['source_modified_by_controller'] is False and report['hidden_tests_used'] is False
missing=Env([dict(returncode=0,output='syntax ok')]);passed,report=validate_submission(missing,['src/pkg/a.py']);assert not passed and len(missing.commands)==1 and 'FOCUSED' in feedback(report)
assert test_selection('python -m pytest -q tests/test_a.py::TestA',['tests/test_a.py'])==dict(runner='pytest',targets=['tests/test_a.py::TestA'])
assert test_selection('python tests/runtests.py model_fields --settings=test_sqlite --parallel 1',['django/__init__.py','tests/model_fields/tests.py'])==dict(runner='django',targets=['model_fields'])
assert test_selection('python -m unittest tests.test_a.TestA',['tests/test_a.py'])==dict(runner='unittest',targets=['tests.test_a.TestA'])
assert test_selection('python -m pytest -q /tmp/fake.py',['tests/test_a.py']) is None
assert test_selection('python -m pytest -q tests/test_a.py; echo ok',['tests/test_a.py']) is None
print('PASS syntax failure short-circuit, real-tests failure feedback, success requires both gates, no patch modification')
folder=Path(__file__).resolve().parent/'context_fixture';folder.mkdir(exist_ok=True)
fixture=folder/'invalid_source.py';fixture.write_text('def probe():\n    try:\nvalue = 1\n    except Exception:\n        pass\n')
before=hashlib.sha256(fixture.read_bytes()).hexdigest()
p=subprocess.run([sys.executable,'-c',SYNTAX_SCRIPT,json.dumps([str(fixture)])],capture_output=True,text=True)
assert p.returncode!=0 and 'ACTUAL_SOURCE_CONTEXT' in p.stdout and '2 indent_columns=4' in p.stdout and '3 indent_columns=0' in p.stdout
assert hashlib.sha256(fixture.read_bytes()).hexdigest()==before
print('PASS actual syntax context and indentation columns, source bytes unchanged')
