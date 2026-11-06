import re
SOURCE_SUFFIXES=('.py','.pyi','.pyx','.pxd','.pxi','.c','.cc','.cpp','.h','.hpp','.rs')
SYSTEM='''You maintain the checked-out Python library in /testbed. Repair the library itself.
The issue's caller examples and expected behavior are acceptance requirements: preserve
their inputs and semantics. A workaround that changes the caller, edits example data,
or adds only a standalone reproduction script is NOT a library repair.
Use the actual repository inventory supplied below; do not guess installed Python paths.
Read relevant library implementation and existing tests, reproduce with unchanged issue
inputs, make a minimal library change, then execute focused existing tests. Existing
tests are protected. Put disposable reproductions in /tmp, not library source files.
Use Python heredoc scripts for multiline editing. No network or package installation.
Each command starts a fresh shell in /testbed; persistent edits remain. Use the supplied
testbed interpreter path. Read errors and change approach; repeated unchanged inspections
are cached and will not be executed again. Changes only to reproduction scripts do not
count as implementation progress.
In the final answer briefly state observations, root-cause hypothesis, and next action.
Provide ONE or TWO fenced bash blocks, executed in order. If an earlier block fails,
later blocks will be skipped. Only final-answer bash blocks execute; never reasoning.
Submit only after a library patch and actual verification, using a sole bash block:
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT
'''
def final_answer(text):
    if '</think>' not in text:raise ValueError('Reasoning did not end; no commands executed.')
    return text.rsplit('</think>',1)[1].strip()
def actions(text):
    values=re.findall(r'```bash\s*\n(.*?)\n```',text,re.S)
    if not 1<=len(values)<=2:raise ValueError('Return one or two final-answer bash blocks.')
    return [v.strip() for v in values]
def package_roots(paths):
    roots=sorted({p.rsplit('/',1)[0] for p in paths if p.endswith('/__init__.py') and '/tests/' not in p and not p.startswith('tests/')})
    if any(p.startswith('src/') and p.endswith(SOURCE_SUFFIXES[2:]) for p in paths):roots.append('src')
    return [p for p in roots if not any(p.startswith(q+'/') for q in roots if q!=p)]
def library_path(path,roots):
    return path.endswith(SOURCE_SUFFIXES) and not any(x in path.split('/') for x in ['tests','test']) and not path.rsplit('/',1)[-1].startswith('test_') and any(path.startswith(p+'/') for p in roots)
def inspection(command):
    command='\n'.join(s for s in command.splitlines() if not s.lstrip().startswith('#')).strip()
    if any(c in command for c in ['\n','>','<',';','&','`','$','/tmp','/opt','..']):return False
    return bool(command) and all(re.match(r'^(cat|grep|rg|find|head|tail|sed\s+-n|git\s+ls-files)\b',part.strip()) for part in command.split('|'))
def review(turn,unchanged,changes):
    return (f'LIBRARY PROGRESS REVIEW turn={turn}, consecutive actions without library change={unchanged}, '
        f'current library changed paths={changes}. Preserve caller inputs. Identify the responsible '
        'existing library function from actual observations, then choose one distinguishing inspection '
        'or minimal library edit. New reproduction scripts and caller workarounds do not repair the package. '
        'Do not repeat known inspections. No task-specific solution is supplied.')
