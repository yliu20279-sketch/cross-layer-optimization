
import pathlib,subprocess,sys,json,shutil
R=pathlib.Path(__file__).resolve().parent;k=int((R/'ROUND_N00').read_text());D=R/f'case{k}'
assert (D/'N00/PASS.json').exists()
run=pathlib.Path.cwd().parent
shutil.copy2(run/'bench.txt',D/'bench.txt')
subprocess.run(sys.argv[1:],check=True,timeout=120)
shutil.copy2(run/'delayInfo.txt',D/'delayInfo.txt')
