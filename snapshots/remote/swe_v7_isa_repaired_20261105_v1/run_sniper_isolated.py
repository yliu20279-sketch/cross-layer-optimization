#!/usr/bin/python3
import os,sys
from pathlib import Path
args=sys.argv[1:];index=args.index('-d')+1
args[index]=str(Path.cwd()/'sniper_stats')
os.environ['MAINT_EVENT_LOG']=str(Path.cwd()/'maintenance.events')
os.execv('/mnt/sda1/h3240101068/swe_v7_log_repair_20261105_v1/sniper/run-sniper',['run-sniper']+args)
