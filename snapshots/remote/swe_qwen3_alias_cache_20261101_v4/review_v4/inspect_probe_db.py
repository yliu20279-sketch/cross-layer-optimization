import sqlite3,json
from pathlib import Path
R=Path(__file__).resolve().parent
for name in ['cache_probe_run_v2','cache_probe_run_v3']:
 c=sqlite3.connect(str(R/name/'sim.stats.sqlite3'));tables=list(c.execute("SELECT name FROM sqlite_master WHERE type='table'"));print(name,tables)
 for (table,) in tables:
  if 'prefix' in table:print(table,list(c.execute('SELECT * FROM '+table+' LIMIT 20')))
