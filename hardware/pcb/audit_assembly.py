#!/usr/bin/python3
"""Audit CAD/CPL consistency and render pin-1 review, not supplier rotation approval."""
from pathlib import Path
import csv,json,hashlib,html
import pcbnew as pcb
root=Path(__file__).resolve().parent
board=root/'source/TC_IO_REVC.kicad_pcb';b=pcb.LoadBoard(str(board))
lookup={f.GetReference():f for f in b.GetFootprints()}
cpl=list(csv.DictReader((root/'pcba/TC_IO_REVC_CPL_DRAFT_NOT_FOR_ORDER.csv').open()))
assert len(cpl)==50 and len({r['Designator'] for r in cpl})==50
for r in cpl:
 f=lookup[r['Designator']]
 assert r['Layer']=='Top'
 assert abs(float(r['Mid X'].removesuffix('mm'))-pcb.ToMM(f.GetPosition().x))<.0001
 assert abs(float(r['Mid Y'].removesuffix('mm'))+pcb.ToMM(f.GetPosition().y))<.0001
 assert abs(float(r['Rotation'])-f.GetOrientationDegrees()%360)<.01
 assert not (f.GetAttributes() & pcb.FP_DNP)
selected=[lookup['U'+str(i)] for i in range(1,8)]+[lookup['VR'+str(i)] for i in range(1,5)]
rows=[]
svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1090">','<rect width="1000" height="1090" fill="white"/>','<text x="30" y="30" font-family="sans-serif" font-size="20">TC IO Rev C: TOP VIEW / IC and VR pad orientation</text>','<text x="30" y="55" font-family="sans-serif" font-size="14">Red = pad 1. CAD orientation only; supplier rotation and pickup centers pending.</text>','<rect x="50" y="90" width="900" height="900" fill="#eef5f0" stroke="#183b36" stroke-width="2"/>']
def pos(x,y):return (50+(x-20)*9,90+(y-20)*9)
for f in selected:
 ref=f.GetReference();x=pcb.ToMM(f.GetPosition().x);y=pcb.ToMM(f.GetPosition().y)
 px,py=pos(x,y)
 svg.append(f'<text x="{px}" y="{py-55}" text-anchor="middle" font-family="sans-serif" font-size="16">{ref}</text>')
 for pad in f.Pads():
  n=pad.GetNumber();a=pad.GetPosition();s=pad.GetSize();xx=pcb.ToMM(a.x);yy=pcb.ToMM(a.y)
  w=pcb.ToMM(s.x)*9;h=pcb.ToMM(s.y)*9
  # All reviewed IC/VR bodies are at zero rotation in this draft.
  assert f.GetOrientationDegrees()==0
  qx,qy=pos(xx,yy);color='#bd3030' if n=='1' else '#d4a94b'
  svg.append(f'<rect x="{qx-w/2}" y="{qy-h/2}" width="{w}" height="{h}" fill="{color}" stroke="#333" stroke-width=".6"/>')
  svg.append(f'<text x="{qx}" y="{qy+2.5}" text-anchor="middle" font-family="sans-serif" font-size="7">{html.escape(n)}</text>')
  rows.append({'Reference':ref,'MPN':f.GetValue(),'Pin':n,'Net':pad.GetNetname(),'Pad X mm':round(xx,4),'Pad Y mm':round(yy,4),'Footprint rotation':f.GetOrientationDegrees(),'Verification':'CAD only; manufacturer review required except documented HC221/VR'})
svg+=['<text x="50" y="1025" font-family="sans-serif" font-size="16">Board outline 100 x 100 mm. Coordinates follow KiCad source.</text>','<text x="50" y="1050" font-family="sans-serif" font-size="16">Unpopulated wire pads and other components are omitted from this review drawing.</text>','</svg>']
(root/'review/IC_VR_pin1_review.svg').write_text('\n'.join(svg)+'\n')
with (root/'pcba/IC_VR_pin-net-review.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n');w.writeheader();w.writerows(rows)
report={'board_sha256':hashlib.sha256(board.read_bytes()).hexdigest(),'cpl_sha256':hashlib.sha256((root/'pcba/TC_IO_REVC_CPL_DRAFT_NOT_FOR_ORDER.csv').read_bytes()).hexdigest(),'cpl_rows_checked':50,'unique_references':50,'all_top':True,'all_anchors_match_board':True,'all_angles_match_kicad':True,'dnp_in_cpl':0,'ic_vr_parts_drawn':11,'pins_reviewed':len(rows),'supplier_rotation_verified':False,'supplier_pickup_center_verified':False,'order_ready':False,'remaining_manufacturer_documents':['MCP3008T-I/SL','SN74HC08DR','MCP100T-300I/TT']}
(root/'reports/assembly-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print('50 CPL rows match CAD; 11 IC/VR orientations and',len(rows),'pin/net assignments exported; supplier approval pending')
