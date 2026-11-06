import os,sys,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
script='set pagination off\nset confirm off\n'
env=os.environ.copy();ld=env.pop('LD_LIBRARY_PATH','')
if ld:script+='set environment LD_LIBRARY_PATH '+ld+'\n'
script+='''python
import threading,os,signal
def interrupt(): os.kill(os.getpid(),signal.SIGINT)
timer=threading.Timer(15,interrupt);timer.daemon=True;timer.start()
end
run
thread apply all bt 14
quit
'''
p=R/'DIRECTORY_PARENT_DEBUG.gdb';p.write_text(script)
sys.exit(subprocess.call(['gdb','-q','-batch','-x',str(p),'--args']+sys.argv[1:],env=env))
