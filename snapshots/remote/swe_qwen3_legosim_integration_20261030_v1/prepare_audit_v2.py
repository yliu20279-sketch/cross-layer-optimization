from pathlib import Path
P=Path('/mnt/sda1/h3240101068/swe_qwen3_legosim_integration_20261030_v1')
R=P/'unified_layers_fifo_v2'
s=(R/'audit_full.py').read_text()
s=s.replace("R/'RUN1.log'", "R/'RUN3.log'").replace("R/'run1/delayInfo.txt'", "R/'run3/delayInfo.txt'")
s=s.replace("log=(R/'RUN3.log').read_text();", "assert j(R/'cpu_data/CPU_PASS.json')['state']=='PASS_LAYER1_PREFILL_DECODE'\nassert 'abort due to EOF' not in (R/'run3/proc_r1_p1_t0/cpu.log').read_text()\nlog=(R/'RUN3.log').read_text();")
s=s.replace("assert delays\n", "assert len(delays)==len((R/'run3/bench.txt').read_text().splitlines())\n")
s=s.replace('external CPU input node layer tag on decode inherits1 but immediately consumed as layer0 per frozen worker','decode input layer tag reset0 before publish; persistent output FIFO spans both messages')
(R/'audit_full.py').write_text(s)
print('audit_v2_prepared')
