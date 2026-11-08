"""Fail-fast supervision of only the launcher/session created by this case."""
import json
import os
import re
import signal
import subprocess
import time


def supervised_run(args,cwd,env,log_path,diagnostic_path):
    started=time.monotonic()
    state={'state':'starting','argv':list(map(str,args)),'cwd':str(cwd)}
    def save():
        state['elapsed_seconds']=time.monotonic()-started
        diagnostic_path.write_text(json.dumps(state,indent=2))
    proc=subprocess.Popen(args,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,errors='replace',bufsize=1,start_new_session=True)
    state.update(state='running',launcher_pid=proc.pid,owned_process_group=proc.pid);save()
    def stop():
        try:os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.wait(timeout=5)
    def interrupted(signum,frame):
        state.update(state='interrupted',signal=signum);save();stop()
        raise InterruptedError(f'case interrupted by signal {signum}; own launcher group stopped')
    old={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
    for s in old:signal.signal(s,interrupted)
    try:
        with log_path.open('w') as log:
            for line in proc.stdout:
                log.write(line);log.flush()
                match=re.search(r'terminate with status\s*=\s*(-?\d+)',line)
                if match and int(match[1])!=0:
                    state.update(state='child_failed',failure_line=line.strip(),child_status=int(match[1]));save()
                    stop()
                    raise RuntimeError('child process failed; stopped own launcher before accepting partial network feedback')
        code=proc.wait();state.update(state='completed',returncode=code);save();return code
    finally:
        if proc.poll() is None or proc.returncode != 0:stop()
        for s,handler in old.items():signal.signal(s,handler)

