import pathlib,json,os,signal
R=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step5_coupled_20261031_v3');v=json.loads((R/'LAUNCH.json').read_text());pid=v['pid'];cmd=pathlib.Path('/proc/'+str(pid)+'/cmdline').read_bytes();assert str(R/'config.yml').encode() in cmd and b'interchiplet' in cmd
(R/'STOP_REASON.json').write_text(json.dumps(dict(reason='controlled stop for owner-batched variant; no numeric threshold changed',native_result='NOT_COMPLETED',replacement='lingbot_step5_coupled_20261031_v4'),indent=2));os.killpg(pid,signal.SIGTERM);print('stopped only verified task PID',pid)
