"""Convert this project's SVG primitives to vector PDFs without changing layout."""
from pathlib import Path
from xml.etree import ElementTree as ET
import re
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import toColor as HexColor

ROOT=Path(__file__).resolve().parent
for font,file in [('TNR','times.ttf'),('TNR-Bold','timesbd.ttf'),('TNR-Italic','timesi.ttf'),('TNR-BoldItalic','timesbi.ttf')]:
    pdfmetrics.registerFont(TTFont(font,str(Path('C:/Windows/Fonts')/file)))

def number(value,default=0):
    if value is None:return default
    return float(str(value).replace('px',''))

def convert(source,target):
    svg=ET.parse(source).getroot()
    _,_,width,height=map(float,svg.attrib['viewBox'].split())
    pdf=canvas.Canvas(str(target),pagesize=(width,height),pageCompression=1,invariant=1)
    pdf.setTitle(source.stem)
    for e in svg:
        tag=e.tag.split('}')[-1];a=e.attrib
        pdf.saveState()
        stroke=a.get('stroke','none');fill=a.get('fill','none')
        if stroke!='none':pdf.setStrokeColor(HexColor(stroke))
        if fill!='none':pdf.setFillColor(HexColor(fill))
        pdf.setLineWidth(number(a.get('stroke-width'),1))
        if 'stroke-dasharray' in a:pdf.setDash([float(x) for x in re.split(r'[ ,]+',a['stroke-dasharray'])])
        if 'fill-opacity' in a:pdf.setFillAlpha(float(a['fill-opacity']))
        if tag=='line':
            pdf.line(number(a['x1']),height-number(a['y1']),number(a['x2']),height-number(a['y2']))
        elif tag=='rect':
            if a.get('width')=='100%':
                pdf.setFillColor(HexColor('#ffffff'));pdf.rect(0,0,width,height,fill=1,stroke=0)
            else:
                x,y,w,h=(number(a.get(k)) for k in ('x','y','width','height'))
                pdf.rect(x,height-y-h,w,h,fill=int(fill!='none'),stroke=int(stroke!='none'))
        elif tag=='circle':
            pdf.circle(number(a['cx']),height-number(a['cy']),number(a['r']),fill=int(fill!='none'),stroke=int(stroke!='none'))
        elif tag=='polygon':
            coords=[float(x) for x in re.split(r'[ ,]+',a['points'].strip())]
            points=list(zip(coords[::2],coords[1::2]))
            p=pdf.beginPath();p.moveTo(points[0][0],height-points[0][1])
            for x,y in points[1:]:p.lineTo(x,height-y)
            p.close();pdf.drawPath(p,fill=int(fill!='none'),stroke=int(stroke!='none'))
        elif tag=='text':
            size=number(a.get('font-size'),20)
            bold=a.get('font-weight') in ('700','bold')
            italic=a.get('font-style')=='italic'
            font='TNR'+('-BoldItalic' if bold and italic else '-Bold' if bold else '-Italic' if italic else '')
            fragments=[(e.text or '',size,0)]
            for child in e:
                raw=child.attrib.get('font-size','70%')
                child_size=size*float(raw[:-1])/100 if raw.endswith('%') else float(raw)
                shift=-size*.22 if child.attrib.get('baseline-shift')=='sub' else 0
                fragments.append((child.text or '',child_size,shift))
                if child.tail:fragments.append((child.tail,size,0))
            length=sum(pdfmetrics.stringWidth(text,font,s) for text,s,_ in fragments)
            x=number(a['x']);y=height-number(a['y'])
            if a.get('dominant-baseline')=='middle':y-=size*.30
            anchor=a.get('text-anchor','start')
            if anchor=='middle':x-=length/2
            elif anchor=='end':x-=length
            pdf.setFillColor(HexColor(a.get('fill','#161616')))
            for text,s,shift in fragments:
                pdf.setFont(font,s);pdf.drawString(x,y+shift,text)
                x+=pdfmetrics.stringWidth(text,font,s)
        else:
            raise ValueError(f'Unsupported SVG primitive: {tag}')
        pdf.restoreState()
    pdf.showPage();pdf.save()
    print(f'Vector PDF: {target.name}')

if __name__=='__main__':
    convert(ROOT/'figures/noc_topology_cs.svg',ROOT/'figures/noc_topology_cs.pdf')
    convert(ROOT/'figures/05_node_configuration_assignment.svg',ROOT/'figures/noc_node_ni.pdf')
