import pathlib,subprocess,time,json,os,signal
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_router_repair_20261028_v2')
py='/mnt/sda1/h3240101068/lingbot_steps1_2_20261027_v1/venv/bin/python'
with (P/'run.log').open('w') as f:
    p=subprocess.Popen([py,'-u',str(P/'run_functional.py')],stdout=f,stderr=subprocess.STDOUT,env=dict(os.environ,CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='8',MKL_NUM_THREADS='8'),start_new_session=True)
    start=time.time();peak=0;reason=None
    while p.poll() is None:
        try:
            status=pathlib.Path('/proc/'+str(p.pid)+'/status').read_text()
            rss=int(next(x for x in status.splitlines() if x.startswith('VmRSS:')).split()[1])*1024
            peak=max(peak,rss)
        except (FileNotFoundError,StopIteration):rss=0
        if rss>24*2**30:reason='RSS_EXCEEDS_24GiB'
        if time.time()-start>2400:reason='TIMEOUT_2400s'
        (P/'PROGRESS.json').write_text(json.dumps(dict(pid=p.pid,seconds=time.time()-start,rss_bytes=rss,peak_rss=peak,reason=reason)))
        if reason:os.killpg(p.pid,signal.SIGTERM);break
        time.sleep(5)
    rc=p.wait()
(P/'EXIT.json').write_text(json.dumps(dict(exit_code=rc,reason=reason,wall_seconds=time.time()-start,peak_rss=peak)))
