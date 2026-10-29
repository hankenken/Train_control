#!/usr/bin/python3
"""Generate TC DRIVE Rev B SCHEMATIC + UNROUTED placement draft, not fabrication."""
from pathlib import Path
import csv,json,uuid,math
import pcbnew as pcb
ROOT=Path(__file__).resolve().parent
SRC=ROOT/'source';SRC.mkdir(exist_ok=True)
NAME='TC_DRIVE_REVB'
parts=[]
def uid(s):return str(uuid.uuid5(uuid.NAMESPACE_URL,'train-control/drive/revb-mini/'+s))
def q(s):return json.dumps(str(s),ensure_ascii=False)
def add(ref,value,footprint,nets,pos,names=None,types=None,note='',populate=True):
 p=dict(ref=ref,value=value,footprint=footprint,nets={str(k):v for k,v in nets.items()},pos=pos,names={str(k):v for k,v in (names or {}).items()},types={str(k):v for k,v in (types or {}).items()},note=note,populate=populate);parts.append(p);return p
wirelib=SRC/'TC_Wire.pretty';wirelib.mkdir(exist_ok=True)
for count,pitch,drill,size,name in [(2,5.08,1.3,3,'Power2'),(3,2.54,1,2,'Control3')]:
 s=f'(footprint "{name}" (version 20241229) (generator "pcbnew") (layer "F.Cu") (attr through_hole)\n'
 s+='(property "Reference" "REF**" (at 0 -3) (layer "F.SilkS") (effects (font (size 1 1))))\n'
 s+=f'(property "Value" "{name}" (at 0 3) (layer "F.Fab") (effects (font (size 1 1))))\n'
 for i in range(count):s+=f'(pad "{i+1}" thru_hole {"rect" if i==0 else "circle"} (at {i*pitch} 0) (size {size} {size}) (drill {drill}) (layers "*.Cu" "*.Mask"))\n'
 (wirelib/(name+'.kicad_mod')).write_text(s+')\n')
# Local DDA footprint retains TI land/mask geometry, uses 0.3 mm plated thermal holes.
thermal_name='DRV8871_DDA_ThermalVias_0p3'
f=pcb.FootprintLoad('/usr/share/kicad/footprints/Package_SO.pretty','SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.95x4.9mm_Mask2.71x3.4mm_ThermalVias')
f.SetFPID(pcb.LIB_ID('TC_Wire',thermal_name))
for pad in f.Pads():
 if pad.GetDrillSize().x:
  pad.SetDrillSize(pcb.VECTOR2I(pcb.FromMM(.3),pcb.FromMM(.3)))
  pad.SetSize(pcb.VECTOR2I(pcb.FromMM(.6),pcb.FromMM(.6)))
pcb.FootprintSave(str(wirelib),f)
add('J1','12V_IN_AFTER_EXTERNAL_FUSE_AND_STOP','TC_Wire:Power2',{1:'VIN_12V',2:'GND'},(28,33,0),types={1:'power_out',2:'power_out'},populate=False)
add('D1','SS34_CANDIDATE','Diode_SMD:D_SMA',{1:'VM',2:'VIN_12V'},(41,33,0),names={1:'K',2:'A'},note='Series reverse polarity diode. Verify selected manufacturer forward loss and pulse current.')
add('D2','SMBJ18A_CANDIDATE','Diode_SMD:D_SMB',{1:'VM',2:'GND'},(54,33,90),names={1:'K',2:'A'},note='Local rail clamp; pulse energy and fuse coordination not validated')
add('C1','470uF_35V_SMD_CANDIDATE','Capacitor_SMD:CP_Elec_10x10.5',{1:'VM',2:'GND'},(68,33,0),names={1:'PLUS',2:'MINUS'},note='Bulk after polarity diode; ESR/ripple/energy verification pending')
channels=['UP_OUT','UP_IN','LOW_OUT','LOW_IN']
for i,ch in enumerate(channels):
 x,y=[(48,57),(91,57),(48,91),(91,91)][i]
 n=i+1
 add('U'+str(n),'DRV8871DDAR','TC_Wire:DRV8871_DDA_ThermalVias_0p3',{1:'GND',2:ch+'_B',3:ch+'_A',4:ch+'_ILIM',5:'VM',6:ch+'_BLUE',7:'GND',8:ch+'_WHITE',9:'GND'},(x,y,0),names={1:'GND',2:'IN2',3:'IN1',4:'ILIM',5:'VM',6:'OUT1',7:'PGND',8:'OUT2',9:'EP_GND'},types={1:'power_in',2:'input',3:'input',4:'passive',5:'power_in',6:'output',7:'power_in',8:'output',9:'power_in'},note='TI SLVSCY9B pinout. DDA exposed pad MUST be soldered and heat-spread. Layout unrouted.')
 add('R'+str(n),'53.6k_1%','Resistor_SMD:R_0805_2012Metric',{1:ch+'_ILIM',2:'GND'},(x-7,y+4,90),note='Itrip nominal 64/53.6=1.194A; 59..69kV plus resistor 1% gives 1.090..1.300A')
 add('C'+str(2+i*2),'100nF_50V_X7R','Capacitor_SMD:C_0805_2012Metric',{1:'VM',2:'GND'},(x+7,y+4,90),note='Place directly at VM/PGND during final layout')
 add('C'+str(3+i*2),'100uF_35V_SMD_CANDIDATE','Capacitor_SMD:CP_Elec_6.3x7.7',{1:'VM',2:'GND'},(x+14,y,0),names={1:'PLUS',2:'MINUS'},note='Local bulk; candidate footprint, specific supplier part not fixed')
 add('J'+str(2+i),'CONTROL_'+ch,'TC_Wire:Control3',{1:'GND',2:ch+'_IN1',3:ch+'_IN2'},(26 if i%2==0 else 72,y-11,0),populate=False,note='Matches TC IO J10-J13 GND/IN1/IN2')
 add('J'+str(6+i),'TURNOUT_'+ch,'TC_Wire:Power2',{1:ch+'_BLUE',2:ch+'_WHITE'},(x+6,y+12,0),populate=False,note='Two-wire turnout only. Blue/white polarity not yet mapped to route.')
 for j,(inp,internal) in enumerate([('IN1','A'),('IN2','B')]):
  k=5+i*4+j*2
  add('R'+str(k),'100R_1%','Resistor_SMD:R_0805_2012Metric',{1:ch+'_'+inp,2:ch+'_'+internal},(x-13,y-5+j*4,0))
  add('R'+str(k+1),'10k_1%','Resistor_SMD:R_0805_2012Metric',{1:ch+'_'+internal,2:'GND'},(x-7,y-5+j*4,0),note='Input pulldown; driver also has internal pulldown')

# Rev B mini: 60 x 45 mm placement candidate, electrical nets unchanged.
positions={'J1':(26,27,0),'D1':(39,26,0),'D2':(49,26,90),'C1':(64.5,26,0)}
for i in range(4):
 x=37 if i%2==0 else 65;y=39.5 if i<2 else 55.5
 positions['U'+str(i+1)]=(x,y,0)
 positions['R'+str(i+1)]=(x-3,y+4,0)
 positions['C'+str(2+i*2)]=(x+5.5,y+3.7,90)
 positions['C'+str(3+i*2)]=(46.5 if i%2==0 else 74.5,y-2,0)
 positions['J'+str(2+i)]=(24.5 if i%2==0 else 53.5,y-4.5,270)
 positions['J'+str(6+i)]=(39 if i%2==0 else 65,y+7.5 if i<2 else 62.4,0)
 for j in range(2):
  k=5+i*4+j*2
  positions['R'+str(k)]=(x-8.5,y-4.5+j*4.5,0)
  positions['R'+str(k+1)]=(x-5.5,y-3.5+j*4.5,90)
for p in parts:p['pos']=positions[p['ref']]
add('#FLG01','PWR_FLAG_VM','',{1:'VM'},(0,0,0),types={1:'power_out'},populate=False,note='Schematic-only annotation: VM is supplied through D1, not a physical source')
root_id=uid('schematic')
font='(effects (font (size 1.0 1.0)))'
def symdef(p):
    ref=p['ref']; keys=sorted(p['nets'],key=int); half=(len(keys)+1)//2
    height=max(5.08,half*2.54)
    body=f'(symbol "TC:{ref}" (pin_names (offset 0.5)) (in_bom {"yes" if p["populate"] else "no"}) (on_board {"yes" if p["footprint"] else "no"})\n'
    for name,val,hide in [('Reference',ref,False),('Value',p['value'],False),('Footprint',p['footprint'],True)]:
        body+=f'(property {q(name)} {q(val)} (at 0 0 0) (effects (font (size 1 1))'+(' (hide yes)' if hide else '')+'))\n'
    body+=f'(symbol "{ref}_0_1" (rectangle (start -10.16 {height/2}) (end 10.16 {-height/2}) (stroke (width 0.254) (type default)) (fill (type background))))\n'
    body+=f'(symbol "{ref}_1_1"\n'
    pins=[]
    for j,k in enumerate(keys):
        side=0 if j<half else 1; row=j if side==0 else j-half
        x=-12.7 if side==0 else 12.7; y=height/2-1.27-row*2.54
        typ=p['types'].get(k,'passive'); name=p['names'].get(k,k)
        body+=f'(pin {typ} line (at {x} {y} {0 if side==0 else 180}) (length 2.54) (name {q(name)} {font}) (number {q(k)} {font}))\n'
        pins.append((k,x,y,side))
    return body+'))', pins, height

schem=f'(kicad_sch (version 20250114) (generator "eeschema") (uuid {root_id}) (paper "A1")\n'
schem+='(title_block (title "TC DRIVE Rev B - UNROUTED DRAFT") (rev "B0-MINI-UNROUTED") (comment 1 "12V ONLY. 4 H-bridges. UNROUTED: NOT FOR FABRICATION."))\n(lib_symbols\n'
defs=[]; library=[]
for p in parts:
    d,pins,h=symdef(p); schem+=d+'\n'; defs.append((pins,h)); library.append(d.replace('"TC:'+p['ref']+'"',q(p['ref']),1))
schem+=')\n'
for i,p in enumerate(parts):
    pins,h=defs[i]; x=50.8+(i%6)*101.6; y=50.8+(i//6)*76.2
    sid=uid(p['ref'])
    schem+=f'(symbol (lib_id "TC:{p["ref"]}") (at {x} {y} 0) (unit 1) (in_bom {"yes" if p["populate"] else "no"}) (on_board {"yes" if p["footprint"] else "no"}) (dnp {"no" if p["populate"] else "yes"}) (uuid {sid})\n'
    for name,val,yy,hide in [('Reference',p['ref'],y-h/2-3,False),('Value',p['value'],y+h/2+3,False),('Footprint',p['footprint'],y,True)]:
        schem+=f'(property {q(name)} {q(val)} (at {x} {yy} 0) (effects (font (size 1 1))'+(' (hide yes)' if hide else '')+'))\n'
    for k,_,_,_ in pins: schem+=f'(pin {q(k)} (uuid {uid(p["ref"]+"pin"+k)}))\n'
    schem+=f'(instances (project "{NAME}" (path "/{root_id}" (reference "{p["ref"]}") (unit 1)))))\n'
    for k,px,py,side in pins:
        xx=x+px; yy=y-py; net=p['nets'][k]
        if net is None:
            schem+=f'(no_connect (at {xx} {yy}) (uuid {uid(p["ref"]+"nc"+k)}))\n';continue
        end=xx+(-5.08 if side==0 else 5.08)
        schem+=f'(wire (pts (xy {xx} {yy}) (xy {end} {yy})) (stroke (width 0) (type default)) (uuid {uid(p["ref"]+"wire"+k)}))\n'
        schem+=f'(label {q(net)} (at {end} {yy} 0) (effects (font (size 1 1)) (justify {"right" if side==0 else "left"} bottom)) (uuid {uid(p["ref"]+"label"+k)}))\n'
schem+=')\n'
(SRC/(NAME+'.kicad_sch')).write_text(schem)
(SRC/'TC.kicad_sym').write_text('(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor")\n'+'\n'.join(library)+')\n')
(SRC/'sym-lib-table').write_text('(sym_lib_table (lib (name "TC") (type "KiCad") (uri "${KIPRJMOD}/TC.kicad_sym") (options "") (descr "Project pin-level symbols")))\n')
libs=sorted({p['footprint'].split(':')[0] for p in parts if p['footprint'] and p['footprint'].split(':')[0]!='TC_Wire'}|{'MountingHole','Fiducial'})
(SRC/'fp-lib-table').write_text('(fp_lib_table\n'+''.join(f'(lib (name "{lib}") (type "KiCad") (uri "${{KICAD9_FOOTPRINT_DIR}}/{lib}.pretty") (options "") (descr ""))\n' for lib in libs)+'(lib (name "TC_Wire") (type "KiCad") (uri "${KIPRJMOD}/TC_Wire.pretty") (options "") (descr "Unpopulated wire pads")))\n')
(SRC/(NAME+'.kicad_pro')).write_text(json.dumps({'meta':{'filename':NAME+'.kicad_pro','version':1},'board':{'design_settings':{'rules':{'min_clearance':0.2,'min_track_width':0.25,'min_via_diameter':0.6,'min_through_hole_diameter':0.2}}},'net_settings':{'classes':[{'name':'Default','clearance':0.2,'track_width':0.25,'via_diameter':0.6,'via_drill':0.3,'microvia_diameter':0.3,'microvia_drill':0.1}]}},indent=2))

board=pcb.BOARD();board.SetCopperLayerCount(2)
mm=pcb.FromMM
def pt(x,y):return pcb.VECTOR2I(mm(x),mm(y))
nets={}
for n in sorted({n for p in parts for n in p['nets'].values() if n}):
 net=pcb.NETINFO_ITEM(board,n);board.Add(net);nets[n]=net
for p in parts:
 if not p['footprint']:continue
 lib,name=p['footprint'].split(':');folder=str(wirelib) if lib=='TC_Wire' else '/usr/share/kicad/footprints/'+lib+'.pretty'
 f=pcb.FootprintLoad(folder,name);assert f is not None,p['footprint']
 f.SetReference(p['ref']);f.SetValue(p['value']);f.SetFPID(pcb.LIB_ID(lib,name));f.SetPosition(pt(*p['pos'][:2]));f.SetOrientationDegrees(p['pos'][2]);f.Value().SetVisible(False)
 path=pcb.KIID_PATH();path.push_back(pcb.KIID(root_id));path.push_back(pcb.KIID(uid(p['ref'])));f.SetPath(path)
 if not p['populate']:f.SetAttributes(f.GetAttributes()|pcb.FP_DNP|pcb.FP_EXCLUDE_FROM_BOM|pcb.FP_EXCLUDE_FROM_POS_FILES)
 for pad in f.Pads():
  if p['nets'].get(pad.GetNumber()):pad.SetNet(nets[p['nets'][pad.GetNumber()]])
 board.Add(f);f.Reference().SetPosition(pt(p['pos'][0],p['pos'][1]-5));f.Reference().SetTextSize(pt(.8,.8))
for i,(x,y) in enumerate([(23,23),(77,23),(23,62),(77,62)],1):
 f=pcb.FootprintLoad('/usr/share/kicad/footprints/MountingHole.pretty','MountingHole_2.2mm_M2');f.SetReference('H'+str(i));f.SetPosition(pt(x,y));f.Reference().SetVisible(False);f.Value().SetVisible(False);board.Add(f)
for a,b in [((20,20),(80,20)),((80,20),(80,65)),((80,65),(20,65)),((20,65),(20,20))]:
 line=pcb.PCB_SHAPE(board);line.SetShape(pcb.SHAPE_T_SEGMENT);line.SetStart(pt(*a));line.SetEnd(pt(*b));line.SetLayer(pcb.Edge_Cuts);line.SetWidth(mm(.05));board.Add(line)
# References on fabrication layer avoid tiny silk text crowding on the mini board.
for f in board.GetFootprints():
 if f.GetReference().startswith(('H','FM')):continue
 f.Reference().SetLayer(pcb.F_Fab)
 f.Reference().SetTextThickness(mm(.10))
 f.Reference().SetTextSize(pt(.8,.8))
# Keep only key IC and wiring references on top silk.
for f in board.GetFootprints():
 ref=f.GetReference()
 if ref.startswith('U'):
  f.Reference().SetLayer(pcb.F_SilkS)
  f.Reference().SetPosition(pt(pcb.ToMM(f.GetPosition().x),pcb.ToMM(f.GetPosition().y)-4.2))
 if ref in ['J1','J2','J3','J4','J5']:
  f.Reference().SetLayer(pcb.F_SilkS)
  f.Reference().SetPosition(pt(pcb.ToMM(f.GetPosition().x),pcb.ToMM(f.GetPosition().y)-2.5))
 if ref in ['J6','J7','J8','J9']:
  f.Reference().SetLayer(pcb.F_SilkS)
  f.Reference().SetPosition(pt(pcb.ToMM(f.GetPosition().x)+2.5,pcb.ToMM(f.GetPosition().y)+1.9))
for i,(x,y) in enumerate([(23,28),(77,28),(57,62)],1):
 f=pcb.FootprintLoad('/usr/share/kicad/footprints/Fiducial.pretty','Fiducial_1mm_Mask2mm');f.SetReference('FM'+str(i));f.SetPosition(pt(x,y));f.Reference().SetVisible(False);f.Value().SetVisible(False);f.SetAttributes(f.GetAttributes()|pcb.FP_EXCLUDE_FROM_BOM|pcb.FP_EXCLUDE_FROM_POS_FILES);board.Add(f)
for txt,x,y in [('TC DRIVE B - 12V',48,21)]:
 t=pcb.PCB_TEXT(board);t.SetText(txt);t.SetPosition(pt(x,y));t.SetTextSize(pt(.8,.8));t.SetTextThickness(mm(.10));t.SetLayer(pcb.F_SilkS);board.Add(t)
pcb.SaveBoard(str(SRC/(NAME+'.kicad_pcb')),board)
for filename,header,rows in [('BOM_DRAFT.csv',['Reference','MPN_or_value','Footprint','Populate','Notes'],[[p['ref'],p['value'],p['footprint'],p['populate'],p['note']] for p in parts]),('connections.csv',['Reference','Pin','Function','Net'],[[p['ref'],k,p['names'].get(k,k),v] for p in parts for k,v in p['nets'].items()])]:
 with (SRC/filename).open('w',newline='') as f:w=csv.writer(f,lineterminator='\n');w.writerow(header);w.writerows(rows)
(SRC/'design_manifest.json').write_text(json.dumps({'board':NAME,'status':'UNROUTED_NOT_FOR_FABRICATION','board_mm':[60,45],'parts':parts},indent=2)+'\n')
print('Driver draft:',len(parts),'logical parts;',sum(p['populate'] for p in parts),'populated; NO TRACKS or manufacturing exports')
