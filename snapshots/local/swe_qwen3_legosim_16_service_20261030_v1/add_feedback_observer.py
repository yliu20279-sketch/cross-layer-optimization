from pathlib import Path
import shutil,subprocess
R=Path(__file__).resolve().parent;S=R/'source/interchiplet'
shutil.copy2(R/'domain_service.h',S/'includes/domain_service.h')
p=S/'includes/net_delay.h';s=p.read_text();needle='if (!has_packet_delay) {';assert s.count(needle)==1
s=s.replace(needle,'swe_domain::feedback(__write_cmd,__read_cmd,has_packet_delay);\n        '+needle);p.write_text(s)
with (R/'BUILD_FEEDBACK_OBSERVER.log').open('w') as f:subprocess.run(['cmake','--build',str(R/'build'),'-j','4'],stdout=f,stderr=subprocess.STDOUT,check=True)
