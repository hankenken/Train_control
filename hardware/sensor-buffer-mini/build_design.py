#!/usr/bin/python3
"""Generate Rev B 45x32mm placement draft. Not a manufacturing release."""
from pathlib import Path
import csv,json,uuid,math
import pcbnew as pcb
ROOT=Path(__file__).resolve().parent
SRC=ROOT/'source';SRC.mkdir(exist_ok=True)
NAME='TC_SENSOR_BUFFER_REVB_MINI'
parts=[]
def uid(s):return str(uuid.uuid5(uuid.NAMESPACE_URL,'train-control/sensor-buffer/revb-mini/'+s))
def q(s):return json.dumps(str(s),ensure_ascii=False)
def add(ref,value,footprint,nets,pos,names=None,types=None,note='',populate=True):
 p=dict(ref=ref,value=value,footprint=footprint,nets={str(k):v for k,v in nets.items()},pos=pos,names={str(k):v for k,v in (names or {}).items()},types={str(k):v for k,v in (types or {}).items()},note=note,populate=populate);parts.append(p);return p
wirelib=SRC/'TC_Wire.pretty';wirelib.mkdir(exist_ok=True)
for count,cols,name in [(3,3,'Sensor3_P2mm'),(10,2,'Output10_2x5_P2mm')]:
 s=f'(footprint "{name}" (version 20241229) (generator "pcbnew") (layer "F.Cu") (attr through_hole)\n'
 s+='(property "Reference" "REF**" (at 0 -2) (layer "F.SilkS") (effects (font (size .7 .7))))\n'
 s+=f'(property "Value" "{name}" (at 0 2) (layer "F.Fab") (effects (font (size .7 .7))))\n'
 for i in range(count):
  x=i%cols*2;y=i//cols*2
  s+=f'(pad "{i+1}" thru_hole {"rect" if i==0 else "circle"} (at {x} {y}) (size 1.6 1.6) (drill .8) (layers "*.Cu" "*.Mask"))\n'
 # courtyard encloses solder pads and wire exit space.
 w=(cols-1)*2;h=(math.ceil(count/cols)-1)*2
 s+=f'(fp_rect (start -1.05 -1.05) (end {w+1.05} {h+1.05}) (stroke (width .05) (type default)) (fill none) (layer "F.CrtYd"))\n'
 (wirelib/(name+'.kicad_mod')).write_text(s+')\n')
# Output harness carries both power and the eight ADC signals. No separate J1.
nets={1:'+3V3',2:'GND',**{i+3:f'ADC{i}' for i in range(8)}}
add('J10','TC_IO_POWER_AND_ADC0_7','TC_Wire:Output10_2x5_P2mm',nets,(39.5,10,0),names={1:'3V3',2:'GND',**{i+3:f'ADC{i}' for i in range(8)}},types={1:'power_out',2:'power_out'},populate=False,note='NO connector. Direct-wire harness:1=3V3,2=GND,3..10=ADC0..7. One common ground replaces eight duplicate output grounds. Verify wire capacity and strain relief.')
for group in range(2):
 x,y=14+15*group,16
 nets={4:'+3V3',11:'GND'};names={4:'VDD',11:'VSS'};types={4:'power_in',11:'power_in'}
 for j,(out,minus,plus) in enumerate([(1,2,3),(7,6,5),(8,9,10),(14,13,12)]):
  i=group*4+j;nets.update({out:f'BUF{i}',minus:f'BUF{i}',plus:f'SENSOR{i}'})
  names.update({out:f'OUT{j}',minus:f'IN{j}-',plus:f'IN{j}+'});types.update({out:'output',minus:'input',plus:'input'})
 add('U'+str(group+1),'MCP6004T-I/SL','Package_SO:SOIC-14_3.9x8.7mm_P1.27mm',nets,(x,y,0),names=names,types=types,note='Unity-gain buffers retained from Rev A. DS20001733L pin roles reviewed. Layout and ADC settling validation pending.')
 add('C'+str(9+group),'100nF_50V_X7R','Capacitor_SMD:C_0805_2012Metric',{1:'+3V3',2:'GND'},(21,10+4*group,0),note='Bypass. Final traces must minimize supply loop.')
for i in range(8):
 x=7+(i%4)*8;y=4 if i<4 else 28
 add('J'+str(2+i),'SENSOR_'+str(i),'TC_Wire:Sensor3_P2mm',{1:'GND',2:'+3V3',3:f'SENSOR{i}'},(x,y,0),populate=False,names={1:'GND',2:'3V3',3:'OUT'},note='Direct wires, .8mm drill /1.6mm pad /2mm pitch. Suggested 26AWG class signal wire; confirm tinned bundle fits. Match Pololu by signal name, not pin number.')
 xx=6 if i<4 else 35.5;yy=9+(i%4)*4.5
 add('R'+str(i+1),'100R_1%','Resistor_SMD:R_0805_2012Metric',{1:f'BUF{i}',2:f'ADC{i}'},(xx,yy,0),note='Output isolation retained; final route and cable load test required')
 add('C'+str(i+1),'1nF_5%_C0G','Capacitor_SMD:C_0805_2012Metric',{1:f'ADC{i}',2:'GND'},(xx,yy+2,0),note='Initial analog filter. Not an overvoltage protector')
add('C11','10uF_10V_X7R','Capacitor_SMD:C_1206_3216Metric',{1:'+3V3',2:'GND'},(21,21,90))

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
schem+='(title_block (title "TC SENSOR BUFFER Rev B MINI - UNROUTED DRAFT") (rev "B0-UNROUTED") (comment 1 "3.3V only. Eight voltage followers. UNROUTED: NOT FOR FABRICATION."))\n(lib_symbols\n'
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
(SRC/(NAME+'.kicad_pro')).write_text(json.dumps({'meta':{'filename':NAME+'.kicad_pro','version':1},'board':{'design_settings':{'rules':{'min_clearance':0.2,'min_track_width':0.25,'min_via_diameter':0.6,'min_through_hole_diameter':0.3}}},'net_settings':{'classes':[{'name':'Default','clearance':0.2,'track_width':0.25,'via_diameter':0.6,'via_drill':0.3,'microvia_diameter':0.3,'microvia_drill':0.1}]}},indent=2))

board=pcb.BOARD();board.SetCopperLayerCount(2)
mm=pcb.FromMM
def pt(x,y):return pcb.VECTOR2I(mm(x),mm(y))
nets={}
for n in sorted({n for p in parts for n in p['nets'].values() if n}):
 net=pcb.NETINFO_ITEM(board,n);board.Add(net);nets[n]=net
for p in parts:
 lib,name=p['footprint'].split(':');folder=str(wirelib) if lib=='TC_Wire' else '/usr/share/kicad/footprints/'+lib+'.pretty'
 f=pcb.FootprintLoad(folder,name);assert f is not None,p['footprint']
 f.SetReference(p['ref']);f.SetValue(p['value']);f.SetFPID(pcb.LIB_ID(lib,name));f.SetPosition(pt(*p['pos'][:2]));f.SetOrientationDegrees(p['pos'][2]);f.Value().SetVisible(False);f.Reference().SetVisible(False)
 path=pcb.KIID_PATH();path.push_back(pcb.KIID(root_id));path.push_back(pcb.KIID(uid(p['ref'])));f.SetPath(path)
 if not p['populate']:f.SetAttributes(f.GetAttributes()|pcb.FP_DNP|pcb.FP_EXCLUDE_FROM_BOM|pcb.FP_EXCLUDE_FROM_POS_FILES)
 for pad in f.Pads():
  if p['nets'].get(pad.GetNumber()):pad.SetNet(nets[p['nets'][pad.GetNumber()]])
 board.Add(f)
for i,(x,y) in enumerate([(2.8,2.8),(42.2,2.8),(2.8,29.2),(42.2,29.2)],1):
 f=pcb.FootprintLoad('/usr/share/kicad/footprints/MountingHole.pretty','MountingHole_2.2mm_M2');f.SetReference('H'+str(i));f.SetPosition(pt(x,y));f.Reference().SetVisible(False);f.Value().SetVisible(False);board.Add(f)
for a,b in [((0,0),(45,0)),((45,0),(45,32)),((45,32),(0,32)),((0,32),(0,0))]:
 line=pcb.PCB_SHAPE(board);line.SetShape(pcb.SHAPE_T_SEGMENT);line.SetStart(pt(*a));line.SetEnd(pt(*b));line.SetLayer(pcb.Edge_Cuts);line.SetWidth(mm(.05));board.Add(line)
def text(t,x,y,size=.8):
 p=pcb.PCB_TEXT(board);p.SetText(t);p.SetPosition(pt(x,y));p.SetTextSize(pt(size,size));p.SetTextThickness(mm(.12));p.SetLayer(pcb.F_SilkS);board.Add(p)
text('3V3 ONLY',22.5,1.3,.8)
text('BUF B / UNROUTED',22.5,30.7,.8)
for i in range(8):
 x=9+(i%4)*8;y=6.2 if i<4 else 25.8;text('S'+str(i),x,y)
text('U1',14,9.8);text('U2',29,9.8)
text('J10',40.5,20.1)
pcb.SaveBoard(str(SRC/(NAME+'.kicad_pcb')),board)
for filename,header,rows in [('BOM_DRAFT.csv',['Reference','MPN_or_value','Footprint','Populate','Notes'],[[p['ref'],p['value'],p['footprint'],p['populate'],p['note']] for p in parts]),('connections.csv',['Reference','Pin','Function','Net'],[[p['ref'],k,p['names'].get(k,k),v] for p in parts for k,v in p['nets'].items()])]:
 with (SRC/filename).open('w',newline='') as f:w=csv.writer(f,lineterminator='\n');w.writerow(header);w.writerows(rows)
(SRC/'design_manifest.json').write_text(json.dumps({'board':NAME,'status':'UNROUTED_NOT_FOR_FABRICATION','board_mm':[45,32],'area_mm2':1440,'old_area_mm2':10000,'area_reduction_percent':85.6,'parts':parts},indent=2)+'\n')
print('Sensor buffer MINI draft:',len(parts),'logical parts;',sum(p['populate'] for p in parts),'SMT;45x32mm;unrouted')
