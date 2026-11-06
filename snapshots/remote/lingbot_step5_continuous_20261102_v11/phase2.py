import pathlib,subprocess,sys,json,shutil
R=pathlib.Path(__file__).resolve().parent;roundno=int((R/'ROUND_N00').read_text());D=R/('case%d'%roundno);run=pathlib.Path.cwd().parent
for rank in range(16):assert (D/('N%02d'%rank)/'PASS.json').exists()
shutil.copy2(run/'bench.txt',D/'bench.txt');c=subprocess.run(sys.argv[1:]);assert c.returncode==0
shutil.copy2(run/'delayInfo.txt',D/'delayInfo.txt');shutil.copy2(pathlib.Path.cwd()/'routing_xy.csv',D/'routing_xy.csv');assert len((D/'bench.txt').read_text().splitlines())==len((D/'delayInfo.txt').read_text().splitlines())>0
(D/'PHASE2_PASS.json').write_text(json.dumps(dict(state='PASS_SELECTED_CONNECTED_REAL_NOC',round=roundno,records=len((D/'bench.txt').read_text().splitlines())),indent=2))
