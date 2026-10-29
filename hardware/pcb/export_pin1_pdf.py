#!/usr/bin/env python3
"""Convert the limited SVG primitives of the pin-1 review to vector PDF."""
from pathlib import Path
from reportlab.pdfgen import canvas
import xml.etree.ElementTree as ET
p=Path(__file__).resolve().parent/'review'
r=ET.parse(p/'IC_VR_pin1_review.svg').getroot()
c=canvas.Canvas(str(p/'IC_VR_pin1_review.pdf'),pagesize=(500,545));c.scale(.5,.5)
for e in r:
 t=e.tag.rsplit('}',1)[-1]
 if t=='rect':
  c.setFillColor(e.attrib.get('fill','white'));c.setStrokeColor(e.attrib.get('stroke',e.attrib.get('fill','white')));c.setLineWidth(float(e.attrib.get('stroke-width','0')))
  x,y,w,h=[float(e.attrib.get(n,0)) for n in ['x','y','width','height']];c.rect(x,1090-y-h,w,h,fill=1,stroke=bool(e.attrib.get('stroke')))
 elif t=='text':
  c.setFillColor('black');c.setFont('Helvetica',float(e.attrib.get('font-size',14)));x=float(e.attrib['x']);y=1090-float(e.attrib['y'])
  (c.drawCentredString if e.attrib.get('text-anchor')=='middle' else c.drawString)(x,y,e.text or '')
c.save()
print('Pin-1 vector PDF exported')
