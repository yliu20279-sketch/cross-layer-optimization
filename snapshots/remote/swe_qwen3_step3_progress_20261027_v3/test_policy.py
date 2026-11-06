from policy import *
assert actions(final_answer('<think>```bash\nwrong\n```</think>```bash\necho one\n```\n```bash\necho two\n```'))==['echo one','echo two']
try:final_answer('<think>```bash\nwrong\n```')
except ValueError:pass
else:raise AssertionError('Unfinished reasoning accepted')
paths=['setup.py','src/pkg/__init__.py','src/pkg/a.py','src/pkg/nested/__init__.py','tests/test_a.py']
roots=package_roots(paths);assert roots==['src/pkg']
assert library_path('src/pkg/a.py',roots) and not library_path('bug_repro.py',roots) and not library_path('src/pkg/tests/test_a.py',roots)
assert library_path('src/backend.cpp',package_roots(['lib/pkg/__init__.py','src/backend.cpp']))
assert not inspection('cat /tmp/current_repro.py')
assert not inspection('cat a.py\npython edit.py') and not inspection('cat <(python edit.py)')
assert inspection('cat src/pkg/a.py | grep foo') and not inspection('cat a.py > b.py') and not inspection('cat a.py; rm a.py')
assert len(actions('```bash\necho a\n```'))==1
print('PASS final-only actions, ordered two-block parsing, package scope, read-only inspection classification')
