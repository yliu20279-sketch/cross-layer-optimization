from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parent;p=R/'audit16_clock.py';s=p.read_text()
old="assert rate==(2.5 if 48 in [s,d] else 1.0) and round(ns*rate)==int(native)"
new="assert (rate in [1.0,2.5] if 48 in [s,d] else rate==1.0) and round(ns*rate)==int(native)"
assert s.count(old)==1;s=s.replace(old,new)
s=s.replace('by=collections.defaultdict(list)','by=collections.defaultdict(list);rates=collections.defaultdict(list)')
needle="by[(s,d,int(v['descriptor']))].append(ns)";assert s.count(needle)==1
s=s.replace(needle,needle+";rates[(s,d,int(v['descriptor']))].append(rate)")
needle="for i,v in enumerate(vals):assert float(v['ready'])==math.ceil(max(by[key][2*i:2*i+2]))";assert s.count(needle)==1
s=s.replace(needle,needle+" and sorted(rates[key][2*i:2*i+2])==([1.0,2.5] if 48 in key[:2] else [1.0,1.0])")
(R/'CLOCK_AUDIT_METHOD_AMENDMENT.json').write_text(json.dumps(dict(reason='Clock is per process: CPU2.5 and gateway1 form each PCIe pair; original predicate mistakenly required gateway2.5 as well',original_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),numerical_output_and_tolerance_unchanged=True,pair_clock_requirement='PCIe exactly one1 and one2.5; other domains both1; readiness ceiling unchanged'),indent=2))
exec(compile(s,str(p),'exec'),{'__file__':str(p)})
