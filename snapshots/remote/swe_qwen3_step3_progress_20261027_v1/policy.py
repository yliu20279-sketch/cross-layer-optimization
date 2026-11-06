"""Final-answer-only actions; reasoning remains in raw request records, never shell/history."""
import re
SYSTEM='''You are an autonomous software repair agent in an offline repository.
Solve the issue by changing implementation source, preserving existing tests.
Use bash tools to inspect implementation, reproduce the symptom, make a minimal fix,
and run relevant tests. Each shell starts fresh in /testbed. Python is
/opt/miniconda3/envs/testbed/bin/python. Use heredoc Python scripts for multiline code;
do not place class/def statements after semicolons. No network or installs.
In each final response state briefly: evidence learned, current root-cause hypothesis,
and what the next command will establish. Then provide exactly ONE fenced bash block.
Avoid repeated diagnostic commands once their result is known. After reproducing,
trace the responsible implementation rather than searching indefinitely for example names.
If an action fails, read its error and change the approach. Keep reads focused.
If stuck, explicitly reject or revise the current hypothesis and inspect a different
relevant implementation path. Do not claim success without executing tests.
When fixed and verified, submit with echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT alone.
'''

def final_answer(text,thinking):
    if '</think>' in text:return text.rsplit('</think>',1)[1].strip()
    if thinking:raise ValueError('Thinking response did not terminate reasoning; no shell action executed.')
    return text.strip()

def action(text):
    blocks=re.findall(r'```bash\s*\n(.*?)\n```',text,re.S)
    if len(blocks)!=1:raise ValueError('Final answer must contain exactly one fenced bash command.')
    return blocks[0].strip()

def reminder(turn,unchanged):
    return (f'PROGRESS REVIEW at turn {turn}; unchanged repository for {unchanged} actions. '
            'Summarize observations already established; state the implementation location and '
            'root-cause hypothesis supported by evidence. If uncertain, choose ONE inspection '
            'that distinguishes hypotheses. If diagnosis is sufficient, edit implementation '
            'and run a focused existing test. Do not repeat known reproductions or empty searches. '
            'No solution is supplied by this review.')
