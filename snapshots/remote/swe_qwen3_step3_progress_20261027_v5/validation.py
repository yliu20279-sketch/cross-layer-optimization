"""Execute generic syntax and existing-test gates, never modify model patches."""
import json,shlex,re
PYTHON='/opt/miniconda3/envs/testbed/bin/python'
SYNTAX_SCRIPT="""import json,sys,pathlib
for name in json.loads(sys.argv[1]):
 p=pathlib.Path(name)
 if not p.is_file(): continue
 raw=p.read_bytes()
 try: compile(raw,name,'exec')
 except SyntaxError as exc:
  lines=raw.decode('utf-8',errors='replace').splitlines()
  position=exc.lineno or 1
  print('ACTUAL_SOURCE_CONTEXT file='+name+' error_line='+str(position))
  for number in range(max(1,position-10),min(len(lines),position+10)+1):
   line=lines[number-1];prefix=line[:len(line)-len(line.lstrip(' \\t'))]
   print(str(number)+' indent_columns='+str(len(prefix.expandtabs(8)))+' | '+line)
  print('END_ACTUAL_SOURCE_CONTEXT: source is unchanged; inspect existing bad edits rather than reinserting them.')
  sys.stdout.flush()
  raise
print('CONTROLLER_SYNTAX_OK')
"""
def execute_check(env,command):
    try:return env.execute(dict(command=command))
    except Exception as exc:return dict(returncode=124,output='CONTROLLER_CHECK_EXECUTION_ERROR: '+type(exc).__name__+': '+str(exc),
        controller_exception=type(exc).__name__,returncode_scope='controller error marker; no shell exit code available')
def test_selection(command,tracked):
    if any(c in command for c in ['\n',';','&','|','>','<','`','$']):return None
    try:args=shlex.split(command)
    except ValueError:return None
    if not args:return None
    runner='pytest'
    if args[0].rsplit('/',1)[-1] in ['python','python3'] and args[1:3]==['-m','pytest']:args=args[3:]
    elif args[0].rsplit('/',1)[-1] in ['python','python3'] and len(args)>1 and args[1].removeprefix('./')=='tests/runtests.py' and 'django/__init__.py' in tracked:
        args=args[2:];runner='django'
    elif args[0].removeprefix('./')=='tests/runtests.py' and 'django/__init__.py' in tracked:args=args[1:];runner='django'
    elif args[0].rsplit('/',1)[-1] in ['python','python3'] and args[1:3]==['-m','unittest']:args=args[3:];runner='unittest'
    elif args[0].rsplit('/',1)[-1]=='pytest':args=args[1:]
    else:return None
    targets=[]
    skip_value=False
    for value in args:
        if skip_value:
            if value!='test_sqlite' and not value.isdigit():return None
            skip_value=False;continue
        if value in ['-q','-v','-x','--disable-warnings']:continue
        if runner=='django':
            if value in ['--settings','--parallel','--verbosity']:skip_value=True;continue
            if value in ['--settings=test_sqlite','--parallel=1','--verbosity=0','--verbosity=1','--verbosity=2','--noinput']:continue
        if value.startswith('-'):return None
        if runner in ['django','unittest']:
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*',value):return None
            prefix='tests/' if runner=='django' else ''
            parts=value.split('.')
            if not any(any(p==prefix+'/'.join(parts[:n])+'.py' or p.startswith(prefix+'/'.join(parts[:n])+'/') for p in tracked if p.startswith('tests/') or '/tests/' in p) for n in range(1,len(parts)+1)):return None
            targets.append(value);continue
        target=value.split('::',1)[0].removeprefix('/testbed/').removeprefix('./')
        if '..' in target.split('/') or target.startswith('/'):return None
        eligible=[p for p in tracked if (p.startswith('tests/') or '/tests/' in p or p.rsplit('/',1)[-1].startswith('test_')) and (p==target or p.startswith(target.rstrip('/')+'/'))]
        if not eligible:return None
        targets.append(value.removeprefix('/testbed/').removeprefix('./'))
    return dict(runner=runner,targets=targets) if targets and not skip_value else None

def validate_submission(env,paths,targets=None,default_full_suite=False):
    runner=targets['runner'] if isinstance(targets,dict) else 'pytest'
    targets=targets['targets'] if isinstance(targets,dict) else targets
    pyfiles=[p for p in paths if p.endswith('.py')]
    script=SYNTAX_SCRIPT
    command=PYTHON+' -c '+shlex.quote(script)+' '+shlex.quote(json.dumps(pyfiles))
    syntax=execute_check(env,command)
    base_command={'pytest':PYTHON+' -m pytest -q','django':PYTHON+' tests/runtests.py --settings=test_sqlite --parallel 1 --verbosity 0','unittest':PYTHON+' -m unittest -q'}[runner]
    report=dict(syntax_command=command,syntax=syntax,tests_command=base_command+''.join(' '+shlex.quote(p) for p in (targets or [])),tests=None,runner=runner,targets=targets,default_full_suite=default_full_suite,
                source_modified_by_controller=False,hidden_tests_used=False)
    if syntax['returncode']!=0:return False,report
    if not targets and not default_full_suite:
        report['test_selection_required']=True;return False,report
    tests=execute_check(env,report['tests_command']);report['tests']=tests
    return tests['returncode']==0,report
def feedback(report):
    if report['syntax']['returncode']!=0:
        return 'SUBMISSION_REJECTED_SYNTAX: no patch was repaired by the controller. Fix the library source and resubmit.\n'+report['syntax'].get('output','')
    if report.get('test_selection_required'):
        return 'SUBMISSION_REJECTED_NO_FOCUSED_TEST_SELECTION: run a standalone focused existing test command. Supported: python -m pytest -q EXISTING_TEST_PATH; for Django: python tests/runtests.py APP_LABEL --settings=test_sqlite --parallel 1; or python -m unittest MODULE.TEST. The controller independently reruns selected original tests on submission. Do not combine registration with editing or other commands.'
    return 'SUBMISSION_REJECTED_EXISTING_TESTS: source syntax passed, but actual original repository tests failed. No hidden tests were used. Read and fix the error, preserving existing tests.\n'+report['tests'].get('output','')
