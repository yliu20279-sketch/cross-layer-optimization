from policy import final_answer,action,reminder
assert action(final_answer('<think>```bash\nWRONG\n```</think>done\n```bash\necho right\n```',True))=='echo right'
for text in ['unfinished reasoning','<think>```bash\nWRONG\n```']:
    try:final_answer(text,True)
    except ValueError:pass
    else:raise AssertionError('Executed unterminated reasoning')
assert action(final_answer('```bash\nprintf ok\n```',False))=='printf ok'
try:action('```bash\na\n```\n```bash\nb\n```')
except ValueError:pass
else:raise AssertionError('Accepted ambiguous action')
assert 'No solution' in reminder(4,4)
print('PASS final-only parsing, incomplete reasoning rejection, ambiguous action rejection, progress review')
