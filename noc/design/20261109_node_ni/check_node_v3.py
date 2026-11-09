"""Node figure layout and owner/control reachability checks, not RTL tests."""
from pathlib import Path
from PIL import Image, ImageFont
import collections
import hashlib
import json
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
meta=json.loads((ROOT/"node_interface_v3.json").read_text(encoding="utf-8"))
assert meta["node_upper_CS_direct_data_link"] is False
owners=meta["configuration_ownership"]
assert len(owners)==9
targets={}
for entry in owners:
    lower=entry["lower_CS"]
    r,c=divmod(lower,3)
    assert entry["owner_node"]==4*r+c
    assert entry["owner_location"]=="NW"
    targets[lower]=[entry["owner_node"],lower]
    if entry["upper_CS"] is not None:
        targets[entry["upper_CS"]]=[entry["owner_node"],lower,entry["upper_CS"]]
assert set(targets)==set(range(13))
assert {e["lower_CS"]:e["upper_CS"] for e in owners if e["upper_CS"] is not None}=={0:9,2:10,6:11,8:12}
counts=collections.Counter()
for r in range(4):
    for c in range(4):
        adj=0
        for cr in range(3):
            for cc in range(3):
                if abs(cr+.5-r)==.5 and abs(cc+.5-c)==.5:
                    near=("N" if cr+.5<r else "S")+("W" if cc+.5<c else "E")
                    back=("N" if r<cr+.5 else "S")+("W" if c<cc+.5 else "E")
                    assert meta["CS_direction_mapping"][near]==back
                    adj+=1
        counts[adj]+=1
assert dict(counts)=={1:4,2:8,4:4}

w,h=meta["diagram_dimensions"]
with Image.open(ROOT/meta["figure_files"][0]) as im:
    assert im.size==(w*2,h*2)
    im.verify()
svg=ET.parse(ROOT/meta["figure_files"][1]).getroot()
assert svg.attrib["viewBox"]==f"0 0 {w} {h}"
ns={"s":"http://www.w3.org/2000/svg"}
texts=[]
for e in svg.findall("s:text",ns):
    size=float(e.attrib["font-size"])
    font=ImageFont.truetype("C:/Windows/Fonts/"+("timesbd.ttf" if e.attrib.get("font-weight")=="700" else "times.ttf"),round(size*2))
    text="".join(e.itertext());width=font.getlength(text)/2
    x,y=float(e.attrib["x"]),float(e.attrib["y"])
    anchor=e.attrib["text-anchor"]
    left=x-width/2 if anchor=="middle" else x-width if anchor=="end" else x
    box=(left,y-size*.43,left+width,y+size*.43)
    assert 0<=box[0] and box[2]<=w and 0<=box[1] and box[3]<=h,(text,box)
    texts.append((text,box))

def intersects(a,b,box):
    low,high=0.0,1.0
    for axis in (0,1):
        delta=b[axis]-a[axis]
        if delta==0:
            if not box[axis]<=a[axis]<=box[axis+2]:return False
        else:
            t1,t2=(box[axis]-a[axis])/delta,(box[axis+2]-a[axis])/delta
            low=max(low,min(t1,t2));high=min(high,max(t1,t2))
            if high<low:return False
    return True

segments=[]
for e in svg.findall("s:line",ns):
    if e.attrib["stroke"]!="white":segments.append(((float(e.attrib["x1"]),float(e.attrib["y1"])),(float(e.attrib["x2"]),float(e.attrib["y2"]))))
for e in svg.findall("s:rect",ns):
    if "x" not in e.attrib:continue
    x,y,ww,hh=(float(e.attrib[k]) for k in ("x","y","width","height"))
    points=[(x,y),(x+ww,y),(x+ww,y+hh),(x,y+hh),(x,y)]
    segments.extend(zip(points,points[1:]))
collisions=[{"text":text,"segment":[a,b]} for a,b in segments for text,box in texts if intersects(a,b,box)]
overlaps=[]
for i,(text,box) in enumerate(texts):
    for text2,box2 in texts[i+1:]:
        if min(box[2],box2[2])>max(box[0],box2[0]) and min(box[3],box2[3])>max(box[1],box2[1]):overlaps.append([text,text2])
assert not collisions,collisions
assert not overlaps,overlaps
files=["draw_node_v3.py","draw_node_v2.py","node_interface_v3.json","check_node_v3.py","README_v3.md","interface_model_checks.py","interface_model_checks.json"]+meta["figure_files"]
report={"scope":"drawing layout, adjacency and fixed configuration reachability only","status":"PASS","nodes_by_CS_count":dict(counts),"configuration_target_paths":targets,"text_line_collisions":collisions,"text_text_overlaps":overlaps,"not_verified":meta["not_verified"],"files":[{"path":name,"sha256":hashlib.sha256((ROOT/name).read_bytes()).hexdigest()} for name in files]}
(ROOT/"static_checks_v3.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8",newline="\n")
print("PASS: layout, 36 Node-CS data links, unique owner and independent configuration route for all 13 CSs. Not RTL verification.")
