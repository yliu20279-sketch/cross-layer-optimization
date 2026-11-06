import pathlib,time,json,subprocess,os
p=pathlib.Path("/mnt/sda1/h3240101068/lingbot_step3_capture_20261028_v1")
pid=int((p/"capture.pid").read_text())
end=time.time()+5500
while time.time()<end:
 if (p/"FINAL_CAPTURE.json").exists():
  env=os.environ.copy();env["CUDA_VISIBLE_DEVICES"]="";env["OMP_NUM_THREADS"]="1";env["MKL_NUM_THREADS"]="1"
  with (p/"audit.log").open("wb",buffering=0) as f:
   r=subprocess.run(["/mnt/sda1/h3240101068/lingbot_steps1_2_20261027_v1/venv/bin/python","-u",str(p/"audit_capture.py")],env=env,stdout=f,stderr=f)
  (p/"AUDIT_EXIT.json").write_text(json.dumps(dict(exit_code=r.returncode,time=time.time())))
  break
 if (p/"CAPTURE_FAILURE.json").exists():break
 proc=pathlib.Path("/proc")/str(pid)/"cmdline"
 if not proc.exists() or b"run_capture.py" not in proc.read_bytes():
  (p/"CAPTURE_PROCESS_EXITED_WITHOUT_FINAL.json").write_text(json.dumps(dict(time=time.time(),pid=pid)))
  break
 time.sleep(8)
