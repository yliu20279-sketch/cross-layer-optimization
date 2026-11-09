"""Draw the two-level NoC and concrete CS gates; enumerate output-decode logic.

This is a design schematic and static truth-table check, not an RTL or timing
validation. Run from any working directory with Python and Pillow installed.
"""
from pathlib import Path
from html import escape
from PIL import Image, ImageDraw, ImageFont
import os,json,math

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'figures';OUT.mkdir(exist_ok=True)
CHECKS=ROOT/'checks';CHECKS.mkdir(exist_ok=True)
INK='#161616';GRAY='#747a80';LIGHT='#aeb6bd';BLUE='#176b91';FAINT='#d3d8dc'

def resolve_fonts():
    # Fonts are not redistributed. An explicit directory takes precedence.
    candidates=[]
    custom=os.environ.get('NOC_FIGURE_FONT_DIR')
    if custom:candidates.append(Path(custom))
    candidates.extend([Path('C:/Windows/Fonts'),Path('/usr/share/fonts/truetype/msttcorefonts'),Path('/usr/share/fonts/truetype/liberation2'),Path('/usr/share/fonts/truetype/liberation'),Path('/usr/share/fonts/truetype/dejavu')])
    families=[('times.ttf','timesbd.ttf','timesi.ttf','timesbi.ttf'),('Times_New_Roman.ttf','Times_New_Roman_Bold.ttf','Times_New_Roman_Italic.ttf','Times_New_Roman_Bold_Italic.ttf'),('LiberationSerif-Regular.ttf','LiberationSerif-Bold.ttf','LiberationSerif-Italic.ttf','LiberationSerif-BoldItalic.ttf'),('DejaVuSerif.ttf','DejaVuSerif-Bold.ttf','DejaVuSerif-Italic.ttf','DejaVuSerif-BoldItalic.ttf')]
    for directory in candidates:
        for regular,bold,italic,bolditalic in families:
            names=[regular,bold,italic,bolditalic]
            if all((directory/name).is_file() for name in names):
                return {(False,False):directory/regular,(False,True):directory/bold,(True,False):directory/italic,(True,True):directory/bolditalic}
    raise FileNotFoundError('Install Times New Roman, Liberation Serif or DejaVu Serif, or set NOC_FIGURE_FONT_DIR.')

FONT_FILES=resolve_fonts()
# Coordinates follow the row-major N0..N15 numbering used in the schematic.
N={f'N{4*r+c}':[c,r] for r in range(4) for c in range(4)}
L={f'L{3*r+c}':[c+.5,r+.5] for r in range(3) for c in range(3)}
pairs={'B0':'L0','B1':'L2','B2':'L6','B3':'L8'}
B={b:L[l] for b,l in pairs.items()}
node_edges=[dict(a=f'L{3*r+c}',b=f'N{4*(r+dr)+c+dc}') for r in range(3) for c in range(3) for dr,dc in [(0,0),(0,1),(1,0),(1,1)]]
upper_edges=[('B0','B1'),('B0','B2'),('B1','B3'),('B2','B3')]
assert len(node_edges)==36 and len(L)==9 and len(B)==4

class Figure:
 def __init__(self,w,h):
  self.w=w;self.h=h;self.im=Image.new('RGB',(w*2,h*2),'white');self.d=ImageDraw.Draw(self.im)
  self.svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><rect width="100%" height="100%" fill="white"/>']
 def line(self,a,b,col=INK,w=1.2):
  self.d.line([tuple(2*v for v in a),tuple(2*v for v in b)],fill=col,width=max(1,round(w*2)))
  self.svg.append(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="{col}" stroke-width="{w}"/>')
 def poly(self,p,fill='white',stroke=INK,w=1.2):
  self.d.polygon([tuple(2*v for v in a) for a in p],fill=fill)
  for a,b in zip(p,p[1:]+p[:1]):self.line(a,b,stroke,w)
  self.svg.append('<polygon points="'+' '.join(f'{x},{y}' for x,y in p)+f'" fill="{fill}" stroke="{stroke}" stroke-width="{w}"/>')
 def rect(self,x,y,w,h,fill='white',stroke=INK):self.poly([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],fill,stroke)
 def circle(self,x,y,r,col=GRAY,fill='white'):
  self.d.ellipse(((x-r)*2,(y-r)*2,(x+r)*2,(y+r)*2),fill=fill,outline=col,width=3)
  self.svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{col}" stroke-width="1.5"/>')
 def font(self,size,italic=False,bold=False):return ImageFont.truetype(str(FONT_FILES[(italic,bold)]),round(size*2))
 def text(self,x,y,t,size=21,bold=False,anchor='start',col=INK):
  ft=self.font(size,bold=bold);self.d.text((x*2,y*2),t,font=ft,fill=col,anchor={'start':'lm','middle':'mm','end':'rm'}[anchor])
  self.svg.append(f'<text x="{x}" y="{y}" font-family="Times New Roman,serif" font-size="{size}" font-weight="{700 if bold else 400}" dominant-baseline="middle" text-anchor="{anchor}" fill="{col}">{escape(t)}</text>')
 def math(self,x,y,base,sub='',suffix='',size=22,anchor='start',col=INK):
  ft=self.font(size,italic=True);sf=self.font(size*.69,italic=True);rf=self.font(size)
  a=ft.getlength(base)/2;b=sf.getlength(sub)/2;c=rf.getlength(suffix)/2;total=a+b+c
  start=x-total/2 if anchor=='middle' else x-total if anchor=='end' else x
  baseline=y+size*.32
  self.d.text((2*start,2*baseline),base,font=ft,fill=col,anchor='ls')
  if sub:self.d.text((2*(start+a),2*(baseline+size*.22)),sub,font=sf,fill=col,anchor='ls')
  if suffix:self.d.text((2*(start+a+b),2*baseline),suffix,font=rf,fill=col,anchor='ls')
  txt=escape(base)
  if sub:txt+=f'<tspan baseline-shift="sub" font-size="69%">{escape(sub)}</tspan>'
  if suffix:txt+=f'<tspan baseline-shift="baseline" font-size="{size}" font-style="normal">{escape(suffix)}</tspan>'
  self.svg.append(f'<text x="{start}" y="{baseline}" font-family="Times New Roman,serif" font-style="italic" font-size="{size}" fill="{col}">{txt}</text>')
  return start+total
 def arrow(self,a,b,col=INK,w=1.2):
  self.line(a,b,col,w);theta=math.atan2(b[1]-a[1],b[0]-a[0]);r=7
  self.poly([b,(b[0]-r*math.cos(theta-.4),b[1]-r*math.sin(theta-.4)),(b[0]-r*math.cos(theta+.4),b[1]-r*math.sin(theta+.4))],col,col)
 def path(self,p,col=INK,w=1.2,arrow=False):
  for a,b in zip(p,p[1:]):self.line(a,b,col,w)
  if arrow:self.arrow(p[-2],p[-1],col,w)
 def andgate(self,x,y,w,h):
  cx=x+w-h/2;cy=y+h/2;r=h/2
  arc=[(cx+r*math.cos(t),cy+r*math.sin(t)) for t in [-math.pi/2+i*math.pi/40 for i in range(41)]]
  self.poly([(x,y),(cx,y)]+arc+[(x,y+h)])
 def save(self,name):
  self.im.save(OUT/(name+'.png'));(OUT/(name+'.svg')).write_text('\n'.join(self.svg+['</svg>']),encoding='utf-8',newline='\n')


d=Figure(2200,1580)
d.text(45,48,'(a) Physical network and basic mesh',28,True)
d.text(1110,48,'(b) Single-connection configurable switches',28,True)
def pr(x,y,z=0):return (80+185*x+123*y,650-65*y-z)
p={n:pr(*xy) for n,xy in N.items()}|{s:pr(*xy) for s,xy in L.items()}|{s:pr(*xy,270) for s,xy in B.items()}
for z,fill in [(0,'#f8f9f9'),(270,'#f1f7fa')]:
 d.poly([pr(x,y,z) for x,y in [(-.15,-.15),(3.15,-.15),(3.15,3.15),(-.15,3.15)]],fill,LIGHT)
mesh=[]
for n,(x,y) in N.items():
 for q,(u,v) in N.items():
  if n<q and abs(x-u)+abs(y-v)==1:
   mesh.append((n,q));d.line(p[n],p[q],FAINT,.8)
for e in node_edges:d.line(p[e['a']],p[e['b']],GRAY,1.1)
for a,b in upper_edges:d.line(p[a],p[b],BLUE,1.6)
for b,l in pairs.items():
 x,y=p[l];u,v=p[b]
 d.line((u,v),(x,y),BLUE,1.1)
for n,(x,y) in p.items():
 if n in N:
  d.poly([(x-22,y-13),(x+22,y-13),(x+27,y+13),(x-17,y+13)])
  d.math(x+2,y,'N',n[1:],size=18,anchor='middle')
 elif n in L:
  d.circle(x,y,16,GRAY,'#f3f4f4');d.math(x,y,'CS',n[1:],size=16,anchor='middle',col=GRAY)
 else:
  d.circle(x,y,21,BLUE,'#e7f2f8');d.math(x,y,'CS',str(9+int(n[1:])),size=20,anchor='middle',col=BLUE)
d.text(80,105,'Nine lower CSs + four upper CSs',22,True)
d.text(80,140,'Each upper CS connects to its corresponding lower CS and two upper neighbors.',19)
d.text(80,711,'Basic 4 x 4 mesh',23,True)
mp={n:(80+185*x+123*y,950-65*y) for n,(x,y) in N.items()}
for a,b in mesh:d.line(mp[a],mp[b],GRAY,1.3)
for n,(x,y) in mp.items():
 d.poly([(x-22,y-13),(x+22,y-13),(x+27,y+13),(x-17,y+13)])
 d.math(x+2,y,'N',n[1:],size=18,anchor='middle')
d.circle(95,1005,13,GRAY);d.text(120,1005,'Lower CS',20)
d.circle(390,1005,15,BLUE);d.text(415,1005,'Upper CS',20)

d.line((80,1047),(120,1047),GRAY);d.text(140,1047,'Node-to-CS links',20)
d.line((420,1047),(460,1047),BLUE);d.text(480,1047,'Upper and inter-level links',20)
d.text(80,1090,'No direct lower-CS-to-lower-CS links.',22,True)
d.text(80,1125,'No direct upper-CS-to-node links. Links have separate transmit/receive wires.',19)


def wire_jump_horizontal(x,y):
 pts=[(x-6*math.cos(t),y-6*math.sin(t)) for t in [i*math.pi/20 for i in range(21)]]
 d.line((x-6,y),(x+6,y),'white',4)
 d.path(pts,'white',4);d.path(pts,INK,1.2)

def inverter(x,y):
 d.poly([(x,y-9),(x,y+9),(x+18,y)])
 d.circle(x+21,y,3,INK,'white')

def expanded_core(y,h,dirs,title,step):
 count=len(dirs);nbits=3 if count==5 else 2
 d.rect(1080,y,1070,h)
 d.text(1110,y+26,title,24,True)
 ry=y+50
 d.rect(1120,ry,970,80)
 d.text(1605,ry+23,'Configuration register',23,True,'middle')
 d.text(1605,ry+57,'Output direction bits; input selection; connection enable (EN)',19,anchor='middle')
 d.text(1115,y-17,'Configuration from NI',18)
 d.path([(1320,y-17),(2050,y-17),(2050,ry)],arrow=True)
 rows=[y+205+j*step for j in range(count)]
 end=rows[-1]+65
 # True and complemented direction bits: actual NOT gates produce the latter.
 rails={}
 inv_y=ry+96
 for k in range(nbits):
  bit=nbits-1-k;qx=1140+k*(85 if nbits==3 else 105);nx=qx+35
  rails[(bit,1)]=qx;rails[(bit,0)]=nx
  d.line((qx,ry+80),(qx,end))
  d.circle(qx,inv_y,2,INK,INK)
  d.line((qx,inv_y),(qx+6,inv_y))
  inverter(qx+6,inv_y)
  d.path([(qx+30,inv_y),(nx,inv_y),(nx,end)])
  # Labels sit beside their rails; no text is drawn over a signal wire.
  d.math(qx-7,inv_y+23,'b',str(bit),size=18,anchor='end')
  d.math(nx+7,inv_y+23,'b',str(bit),size=18)
  d.line((nx+7,inv_y+12),(nx+17,inv_y+12))
 ex=1395
 d.line((ex,ry+80),(ex,end));d.text(ex+8,inv_y+23,'EN',18)
 # Common two-bit/one-bit MUX selection, separate from direction decoding.
 sx=1510
 d.line((sx,ry+80),(sx,end));d.math(sx+12,ry+95,'SEL','in',size=19)
 for j,(target,cy) in enumerate(zip(dirs,rows)):
  # Each output gets one concrete minterm AND gate.
  d.andgate(1430,cy-27,65,60)
  d.text(1462,cy-43,format(j,f'0{nbits}b'),18,anchor='middle')
  yy=[cy-18,cy-6,cy+6,cy+18] if nbits==3 else [cy-12,cy,cy+12]
  for k in range(nbits):
   bit=nbits-1-k;x=rails[(bit,(j>>bit)&1)]
   d.circle(x,yy[k],2,INK,INK)
   d.line((x,yy[k]),(1430,yy[k]))
  d.circle(ex,yy[-1],2,INK,INK);d.line((ex,yy[-1]),(1430,yy[-1]))
  # Decoded enable reaches the matching output gate via an actual wire.
  ey=cy+45
  d.path([(1495,cy+3),(1500,cy+3),(1500,ey),(1850,ey),(1850,cy+18),(1890,cy+18)],arrow=True)
  wire_jump_horizontal(sx,ey)
  choices=[q for q in dirs if q!=target]
  gap=18 if count==5 else 25
  for k,src in enumerate(choices):
   yy0=cy+(k-(len(choices)-1)/2)*gap
   d.text(1535,yy0,str(k),16)
   d.math(1560,yy0,'I',src,size=21)
   d.arrow((1620,yy0),(1675,yy0))
  d.poly([(1675,cy-43),(1745,cy-25),(1745,cy+25),(1675,cy+43)])
  d.text(1709,cy,f'{count-1}:1',22,anchor='middle')
  d.line((1745,cy),(1890,cy))
  d.andgate(1890,cy-17,55,55)
  d.arrow((1945,cy+10),(2050,cy+10))
  d.math(2070,cy+10,'O',target,size=21)
  sel_y=cy+60
  d.circle(sx,sel_y,2,INK,INK)
  d.path([(sx,sel_y),(1710,sel_y),(1710,cy+34)],arrow=True)
 d.text(1110,y+h-48,'Direction code above each AND gate selects its output; only one gate can be enabled.',18)
 d.text(1110,y+h-20,'A bar means NOT; a dot means a junction. Input codes follow the listed order (0 at top).',18)

expanded_core(115,750,['NW','NE','SW','SE','U'],'Lower CS: five directions, five 4:1 MUXs',102)
expanded_core(970,545,['E','S','D'],'Upper CS: east, south and down (CS9 shown)',96)
d.text(1110,895,'NW / NE / SW / SE: corner nodes. U: the corresponding upper CS.',20)
d.text(1110,927,'I / O: input / output. Same-direction inputs are excluded from each MUX.',19)
d.text(1110,1550,'E / W / N / S: physical compass directions. D: down to the corresponding lower CS.',19)

# Use the actual compass directions at each upper-switch position.
d.text(80,1210,'Upper CS',22,True)
d.text(300,1210,'Horizontal directions',22,True)
d.text(680,1210,'Down to',22,True)
for row,(cs,compass,lower) in enumerate([(9,'E, S',0),(10,'W, S',2),(11,'E, N',6),(12,'W, N',8)]):
 yy=1255+row*45
 d.math(80,yy,'CS',str(cs),size=22)
 d.text(300,yy,compass,22)
 d.math(680,yy,'CS',str(lower),size=22)


d.save('noc_topology_cs')

checks={}
for label,n in [('lower',5),('upper',3)]:
 bits=3 if n==5 else 2
 for en in (0,1):
  for word in range(1<<bits):
   terms=[]
   for j in range(n):
    terms.append(en & int(all(((word>>b)&1)==((j>>b)&1) for b in range(bits))))
   assert sum(terms)<=1
   assert terms==[int(en==1 and word==j) for j in range(n)]
 checks[label]={'direction_bits':bits,'direction_codes_checked':1<<bits,'enable_values_checked':2,'at_most_one_output':True,'unused_codes_all_off':True}
(CHECKS/'output_decode_truth_table.json').write_text(json.dumps(checks,indent=2),encoding='utf-8',newline='\n')
print('Saved gate-expanded PNG/SVG; output-decode truth tables pass. No RTL validation claimed.')
