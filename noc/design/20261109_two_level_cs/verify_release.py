"""Verify this small drawing package; never run simulation or network commands."""
from pathlib import Path
from PIL import Image
import hashlib,json,xml.etree.ElementTree as ET

root=Path(__file__).resolve().parent
required=['.gitattributes','README.md','requirements.txt','draw_figures.py','verify_release.py','figures/noc_topology_cs.png','figures/noc_topology_cs.svg','checks/output_decode_truth_table.json']
for rel in required:
    assert (root/rel).is_file(),f'Missing {rel}'
with Image.open(root/'figures/noc_topology_cs.png') as im:
    assert im.size==(4400,3160)
    im.verify()
svg=ET.parse(root/'figures/noc_topology_cs.svg').getroot()
assert svg.attrib['viewBox']=='0 0 2200 1580'
table=json.loads((root/'checks/output_decode_truth_table.json').read_text(encoding='utf-8'))
for name,bits in [('lower',3),('upper',2)]:
    assert table[name]==dict(direction_bits=bits,direction_codes_checked=1<<bits,enable_values_checked=2,at_most_one_output=True,unused_codes_all_off=True)
for rel in ['draw_figures.py','verify_release.py']:
    text=(root/rel).read_text(encoding='utf-8')
    assert ('C:'+'/'+'Users/') not in text
    compile(text,rel,'exec')
report={'scope':'drawing-package integrity and static output-decode checks only','status':'PASS','png_size':[4400,3160],'svg_viewbox':[0,0,2200,1580],'files':[dict(path=rel,bytes=(root/rel).stat().st_size,sha256=hashlib.sha256((root/rel).read_bytes()).hexdigest()) for rel in required]}
(root/'checks/package_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print('PASS: standalone drawing sources, figures, dimensions and static truth tables; SHA-256 manifest written.')
