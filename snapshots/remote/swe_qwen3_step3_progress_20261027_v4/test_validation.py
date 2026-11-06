from validation import validate_submission,feedback,test_selection
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
