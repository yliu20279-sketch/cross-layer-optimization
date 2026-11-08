"""Project-private YoWASP entry point; no global Python installation."""
from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools/py'))
os.environ.setdefault('YOWASP_CACHE_DIR',str(ROOT/'tools/cache'))
from yowasp_yosys import run_yosys
if __name__=='__main__':raise SystemExit(run_yosys(sys.argv[1:]))
