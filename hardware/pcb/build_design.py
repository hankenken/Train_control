#!/usr/bin/python3
"""Generate the review prototype using KiCad 9 pcbnew (system Python).
Routing is a separate step. Never export an order ZIP without checking DRC.
"""
from pathlib import Path
import csv, json, uuid, math
import pcbnew as pcb

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'source'
SRC.mkdir(parents=True, exist_ok=True)
NAME = 'TC_IO_REVC'
parts = []
def uid(s): return str(uuid.uuid5(uuid.NAMESPACE_URL, 'train-control/pcb/revc/'+s))
def q(s): return json.dumps(str(s), ensure_ascii=False)
def add(ref, value, footprint, nets, pos, names=None, types=None, note=''):
    part = dict(ref=ref, value=value, footprint=footprint, nets={str(k):v for k,v in nets.items()},
                pos=pos, names={str(k):v for k,v in (names or {}).items()},
                types={str(k):v for k,v in (types or {}).items()}, note=note)
    parts.append(part); return part

dip16='Package_SO:SOIC-16_3.9x9.9mm_P1.27mm'
dip14='Package_SO:SOIC-14_3.9x8.7mm_P1.27mm'
cap='Capacitor_SMD:C_0805_2012Metric'
res='Resistor_SMD:R_0805_2012Metric'
j3='Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical'
h2='Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical'
channels=['UP_OUT','UP_IN','LOW_OUT','LOW_IN']
gpios=[(5,6,12),(13,16,19),(20,21,26),(17,27,22)]
gpio_phys={5:29,6:31,12:32,13:33,16:36,19:35,20:38,21:40,26:37,17:11,27:13,22:15}
pinmap={1:'+3V3',3:'SDA',5:'SCL',16:'ARM',19:'MOSI',21:'MISO',23:'SCLK',24:'ADC_CS'}
for p in [6,9,14,20,25,30,34,39]: pinmap[p]='GND'
for ch,gs in zip(channels,gpios):
    for sig,g in zip(['P','N','TRIG'],gs): pinmap[gpio_phys[g]]=ch+'_'+sig
pi_types={p:('power_out' if n in ['+3V3','GND'] and p in [1,6] else 'passive') for p,n in pinmap.items()}
for p,n in pinmap.items():
    if n not in ['+3V3','GND']: pi_types[p]='input' if n=='MISO' else 'bidirectional' if n in ['SDA','SCL'] else 'output'
add('J1','PI4_40PIN_CABLE','Connector_IDC:IDC-Header_2x20_P2.54mm_Vertical',
    {p:pinmap.get(p) for p in range(1,41)}, (30,40,0), types=pi_types,
    note='Separate board, keyed ribbon cable; no 5V connection; verify pin 1 at both ends')
for i in range(8):
    add('J'+str(i+2),f'SENSOR_{i}',j3,{1:'GND',2:'SENSOR_3V3',3:f'AN{i}'},(70+12*i,30,0),
        names={1:'GND',2:'VCC_3V3',3:'OUT'},note='Board-specific pin order, not universal sensor pinout')
add('JP1','SENSOR_POWER_OFF_DEFAULT',h2,{1:'+3V3',2:'SENSOR_3V3'},(55,30,0),note='NO SHUNT until sensor current budget is verified')
adc={i+1:f'AN{i}' for i in range(8)}
adc.update({9:'GND',10:'ADC_CS',11:'MOSI',12:'MISO',13:'SCLK',14:'GND',15:'+3V3',16:'+3V3'})
add('U1','MCP3008T-I/SL',dip16,adc,(76,50,0),
    names={**{i+1:f'CH{i}' for i in range(8)},9:'DGND',10:'CS',11:'DIN',12:'DOUT',13:'CLK',14:'AGND',15:'VREF',16:'VDD'},
    types={9:'power_in',10:'input',11:'input',12:'output',13:'input',14:'power_in',15:'power_in',16:'power_in'},
    note='10-bit ADC, 3.3V supply/reference; sensor outputs must stay within 0..3.3V')
for timer_index in range(2):
    nets={8:'GND',16:'+3V3'}
    names={8:'GND',16:'VCC'}; types={8:'power_in',16:'power_in'}
    for half in range(2):
        ch=channels[timer_index*2+half]
        a,b,clr,ce,rc,qp,qn=([1,2,3,14,15,13,4] if half==0 else [9,10,11,6,7,5,12])
        nets.update({a:'GND',b:ch+'_TRIG',clr:'CLEAR_N',ce:ch+'_CE',rc:ch+'_RC',qp:ch+'_Q',qn:None})
        names.update({a:'A_N',b:'B',clr:'CLR_N',ce:'CEXT',rc:'RCEXT',qp:'Q',qn:'Q_N'})
        types.update({a:'input',b:'input',clr:'input',ce:'passive',rc:'passive',qp:'output',qn:'output'})
    add('U'+str(2+timer_index),'SN74HC221DR',dip16,nets,(117,53+36*timer_index,0),names,types,
        note='HC, NOT LS/HCT. Timing RC unverified at 3.3V: measure before load connection')

gatepins=[(1,2,3),(4,5,6),(9,10,8),(12,13,11)]
for gi in range(2):
    nets={7:'GND',14:'+3V3'}; names={7:'GND',14:'VCC'}; types={7:'power_in',14:'power_in'}
    for gate,(a,b,o) in enumerate(gatepins):
        ch=channels[gi*2+gate//2]; d='P' if gate%2==0 else 'N'
        nets.update({a:ch+'_'+d,b:ch+'_Q',o:ch+'_IN'+str(gate%2+1)})
        names.update({a:f'{gate+1}A',b:f'{gate+1}B',o:f'{gate+1}Y'})
        types.update({a:'input',b:'input',o:'output'})
    add('U'+str(4+gi),'SN74HC08DR',dip14,nets,(151,53+36*gi,0),names,types)
nets={7:'GND',14:'+3V3',1:'ARM',2:'POWER_GOOD',3:'CLEAR_N',4:'GND',5:'GND',6:None,
      9:'GND',10:'GND',8:None,12:'GND',13:'GND',11:None}
add('U6','SN74HC08DR',dip14,nets,(55,101,0),types={7:'power_in',14:'power_in',1:'input',2:'input',3:'output',
    4:'input',5:'input',6:'output',9:'input',10:'input',8:'output',12:'input',13:'input',11:'output'})
add('U7','MCP100T-300I/TT','Package_TO_SOT_SMD:SOT-23',
    {1:'POWER_GOOD',2:'+3V3',3:'GND'},(83,102,0),
    names={1:'RESET_N',2:'VDD',3:'VSS'},types={1:'output',2:'power_in',3:'power_in'},
    note='RESET_N=pin1,VDD=pin2,VSS=pin3. Manufacturer/package pinout must be independently checked')

pulled=[ch+'_'+s for ch in channels for s in ['P','N','TRIG']]+['ARM']+[ch+'_IN'+str(i) for ch in channels for i in [1,2]]
assert len(pulled)==21
for ri,net in enumerate(pulled,6):
    add('R'+str(ri),'10k_1%',res,{1:net,2:'GND'},(44,105,0),note='Individual SMT pulldown replacing the former SIP resistor networks')

for i,ch in enumerate(channels):
    x,y=[(102,50),(102,65),(102,86),(102,101)][i]
    add('R'+str(i+1),'150k_1%',res,{1:'+3V3',2:ch+'_ADJ'},(x,y,90))
    add('VR'+str(i+1),'3224W-1-104E','Potentiometer_SMD:Potentiometer_Bourns_3224W_Vertical',
        {1:ch+'_ADJ',2:ch+'_RC',3:ch+'_RC'},(51+14*i,40.5,0),
        names={1:'CCW',2:'WIPER',3:'CW'},
        note='100k multi-turn trimmer, series with 150k. Wiper pin2 tied to pin3; verify CW direction and pulse width on bench')
    add('C'+str(i+1),'470nF_5%_X7R_50V','Capacitor_SMD:C_1206_3216Metric',
        {1:ch+'_CE',2:ch+'_RC'},(x-8,y+1,90),note='Floating timing MLCC: CEXT to RCEXT. Verify DC bias, temperature and actual pulse width; no guaranteed timing limit')
for i,(ref,x,y) in enumerate([('U1',85,76),('U2',130,73),('U3',130,109),('U4',164,72),('U5',164,108),('U6',69,120),('U7',83,96)]):
    add('C'+str(5+i),'100nF_X7R_50V',cap,{1:'+3V3',2:'GND'},(x,y,0),note='IC bypass; keep close')
add('C12','100nF_X7R_50V',cap,{1:'+3V3',2:'GND'},(83,44,0),note='ADC reference bypass')
add('C13','10uF_X7R_25V','Capacitor_SMD:C_1206_3216Metric',{1:'+3V3',2:'GND'},(54,41,0),note='Nonpolar MLCC bulk bypass; check effective capacitance')
add('R5','10k_1%',res,{1:'+3V3',2:'ADC_CS'},(67,57,90))
for i,ch in enumerate(channels):
    add('J'+str(i+10),ch+'_DRV',j3,{1:'GND',2:ch+'_IN1',3:ch+'_IN2'},(179,47+23*i,90),
        names={1:'GND',2:'IN1',3:'IN2'},note='Logic only to separate DRV8871 module. NEVER connect turnout or 12V here')
add('J14','I2C_FUTURE','Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical',
    {1:'GND',2:'+3V3',3:'SDA',4:'SCL'},(37,105,0),note='Reserved only; no signal/LED output circuitry fitted')
add('TP1','CLEAR_N',h2,{1:'CLEAR_N',2:'GND'},(72,112,0))
add('TP2','POWER_GOOD',h2,{1:'POWER_GOOD',2:'GND'},(92,115,0))
for i,ch in enumerate(channels):
    add('TP'+str(i+3),ch+'_Q',h2,{1:ch+'_Q',2:'GND'},(138,45+20*i,0))

# Rev C: all populated components are SMT; connectors are omitted and
# replaced by plated wire-pad groups. VRs are included in factory assembly.
placements = {
    'J1':(29,48,0), 'JP1':(23.5,36,0),
    'U1':(49,55,0), 'U2':(73,55,0), 'U3':(73,86,0),
    'U4':(99,55,0), 'U5':(99,86,0), 'U6':(49,86,0), 'U7':(101,111,0),
    'C1':(85,51,90), 'C2':(85,65,90), 'C3':(85,82,90), 'C4':(85,96,90),
    'R1':(89.5,51,90), 'R2':(89.5,65,90), 'R3':(89.5,82,90), 'R4':(89.5,96,90),
    'C5':(59,53.5,0), 'C6':(70,70,0), 'C7':(77,99,0), 'C8':(97,69,0),
    'C9':(98,100,0), 'C10':(47,99,0), 'C11':(108,105,0), 'C12':(58,70,0),
    'C13':(38.5,105.5,0), 'R5':(40,55,90), 'J14':(34,110,0),
    'TP1':(81,113,0), 'TP2':(88,113,0),
    'TP3':(60,47,0), 'TP4':(60,62,0), 'TP5':(60,78,0), 'TP6':(60,94,0),
    'VR1':(49,41,0), 'VR2':(63,41,0), 'VR3':(77,41,0), 'VR4':(98,41,0),
}
for i in range(21):placements['R'+str(i+6)]=(44+4.5*(i%7),103+5*(i//7),0)
for i in range(8): placements['J'+str(i+2)]=(29+11.2*i,33,0)
for i in range(4): placements['J'+str(i+10)]=(113,49+16*i,90)
assert {p['ref'] for p in parts} == set(placements)
for p in parts: p['pos']=placements[p['ref']]
wire_parts=[p for p in parts if p['ref'].startswith(('J','TP'))]
for p in parts:
    p['populate']=p not in wire_parts
    if not p['populate']:
        rows=2 if p['ref']=='J1' else 1
        count=len(p['nets']);pitch=2.54 if rows==2 or count!=3 else 2.50
        p['footprint']=f'TC_Wire:WirePads_{rows}x{count//rows:02d}_P{pitch:.2f}'
        p['value']='WIRE_PADS_NO_COMPONENT'
        p['note']='Plated wire/test pads only. No connector or header component is fitted.'
assert sum(p['populate'] for p in parts)==50 and len(wire_parts)==21

# Self-contained project footprints for direct soldering; no connector body.
wirelib=SRC/'TC_Wire.pretty';wirelib.mkdir(exist_ok=True)
for p in wire_parts:
    name=p['footprint'].split(':')[1]
    if (wirelib/(name+'.kicad_mod')).exists():continue
    count=len(p['nets']);rows=2 if p['ref']=='J1' else 1;pitch=2.54 if rows==2 or count!=3 else 2.50
    module=f'(footprint "{name}" (version 20241229) (generator "pcbnew") (layer "F.Cu") (attr through_hole exclude_from_pos_files exclude_from_bom)\n'
    module+='(property "Reference" "REF**" (at 0 -3 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))\n'
    module+=f'(property "Value" "{name}" (at 0 -4.5 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))\n'
    for number in range(1,count+1):
        x=(number-1)%2*pitch if rows==2 else (number-1)*pitch
        y=(number-1)//2*pitch if rows==2 else 0
        size=1.7 if rows==2 else 2.0;drill=.9 if rows==2 else 1.0
        module+=f'(pad "{number}" thru_hole {"rect" if number==1 else "circle"} (at {x} {y}) (size {size} {size}) (drill {drill}) (layers "*.Cu" "*.Mask"))\n'
    module+=')\n';(wirelib/(name+'.kicad_mod')).write_text(module)

root_id=uid('schematic')
font='(effects (font (size 1.0 1.0)))'
def symdef(p):
    ref=p['ref']; keys=sorted(p['nets'],key=int); half=(len(keys)+1)//2
    height=max(5.08,half*2.54)
    body=f'(symbol "TC:{ref}" (pin_names (offset 0.5)) (in_bom {"yes" if p["populate"] else "no"}) (on_board yes)\n'
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
schem+='(title_block (title "TC IO Rev C - REVIEW PROTOTYPE") (rev "C0-DRAFT") (comment 1 "3.3V logic only. Separate DRV8871 modules. No 12V/coil terminals."))\n(lib_symbols\n'
defs=[]; library=[]
for p in parts:
    d,pins,h=symdef(p); schem+=d+'\n'; defs.append((pins,h)); library.append(d.replace('"TC:'+p['ref']+'"',q(p['ref']),1))
schem+=')\n'
for i,p in enumerate(parts):
    pins,h=defs[i]; x=50.8+(i%8)*101.6; y=50.8+(i//8)*76.2
    sid=uid(p['ref'])
    schem+=f'(symbol (lib_id "TC:{p["ref"]}") (at {x} {y} 0) (unit 1) (in_bom {"yes" if p["populate"] else "no"}) (on_board yes) (dnp {"no" if p["populate"] else "yes"}) (uuid {sid})\n'
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
libs=sorted({p['footprint'].split(':')[0] for p in parts if p['footprint'].split(':')[0]!='TC_Wire'}|{'MountingHole','Fiducial'})
(SRC/'fp-lib-table').write_text('(fp_lib_table\n'+''.join(f'(lib (name "{lib}") (type "KiCad") (uri "${{KICAD9_FOOTPRINT_DIR}}/{lib}.pretty") (options "") (descr ""))\n' for lib in libs)+'(lib (name "TC_Wire") (type "KiCad") (uri "${KIPRJMOD}/TC_Wire.pretty") (options "") (descr "Unpopulated wire pads")))\n')
(SRC/(NAME+'.kicad_pro')).write_text(json.dumps({'meta':{'filename':NAME+'.kicad_pro','version':1},'board':{'design_settings':{'rules':{'min_clearance':0.2,'min_track_width':0.25,'min_via_diameter':0.6,'min_through_hole_diameter':0.3}}},'net_settings':{'classes':[{'name':'Default','clearance':0.2,'track_width':0.25,'via_diameter':0.6,'via_drill':0.3,'microvia_diameter':0.3,'microvia_drill':0.1}]}},indent=2))

board=pcb.BOARD()
board.SetCopperLayerCount(2)
mm=pcb.FromMM
def point(x,y):return pcb.VECTOR2I(mm(x),mm(y))
nets={}
for name in sorted({n for p in parts for n in p['nets'].values() if n}):
    net=pcb.NETINFO_ITEM(board,name);board.Add(net);nets[name]=net

def text(s,x,y,size=1.0):
    t=pcb.PCB_TEXT(board);t.SetText(s);t.SetPosition(point(x,y));t.SetTextSize(point(size,size));t.SetTextThickness(mm(.15));t.SetLayer(pcb.F_SilkS);board.Add(t)
    return t
for p in parts:
    lib,fpname=p['footprint'].split(':')
    fp=pcb.FootprintLoad(str(wirelib) if lib=='TC_Wire' else '/usr/share/kicad/footprints/'+lib+'.pretty',fpname)
    if fp is None:raise ValueError(p['footprint'])
    fp.SetReference(p['ref']);fp.SetValue(p['value']);fp.SetPosition(point(*p['pos'][:2]));fp.SetOrientationDegrees(p['pos'][2])
    fp.SetFPID(pcb.LIB_ID(lib,fpname))
    if not p['populate']:fp.SetAttributes(fp.GetAttributes()|pcb.FP_DNP|pcb.FP_EXCLUDE_FROM_BOM|pcb.FP_EXCLUDE_FROM_POS_FILES)
    path=pcb.KIID_PATH(); path.push_back(pcb.KIID(root_id)); path.push_back(pcb.KIID(uid(p['ref']))); fp.SetPath(path)
    fp.Value().SetVisible(False)
    for pad in fp.Pads():
        net=p['nets'].get(pad.GetNumber())
        if net:pad.SetNet(nets[net])
    board.Add(fp)
    fp.Reference().SetPosition(point(p['pos'][0],p['pos'][1]-4))
    fp.Reference().SetTextAngle(pcb.EDA_ANGLE(0,pcb.DEGREES_T))
    if p['ref']=='J1': fp.Reference().SetPosition(point(29,41))
    if p['ref'] in ['J10','J11','J12','J13']:
        fp.Reference().SetPosition(point(114,p['pos'][1]-10))
    if p['ref']=='U7': fp.Reference().SetPosition(point(101,116))
    reference_positions={'C12':(57,73),
                         'C13':(39,115), 'C5':(59,56.8), 'C6':(79,70), 'TP3':(60,44.4)}
    if p['ref'] in reference_positions:fp.Reference().SetPosition(point(*reference_positions[p['ref']]))
    fp.Reference().SetTextSize(point(1,1));fp.Reference().SetTextThickness(mm(.15))
    if p['ref'].startswith('VR'):
        fp.Reference().SetPosition(point(p['pos'][0],p['pos'][1]-3.6))
        fp.Reference().SetTextSize(point(.8,.8))
    if p['ref'].startswith('R') and p['ref'][1:].isdigit() and int(p['ref'][1:])>=6:
        fp.Reference().SetPosition(point(p['pos'][0],p['pos'][1]-1.8))
    if p['ref'] in ['U1','U2','U3','U4','U5','U6']:
        fp.Reference().SetPosition(point(p['pos'][0],p['pos'][1]-6.5))
for i,(x,y) in enumerate([(24,24),(116,24),(24,116),(116,116)]):
    fp=pcb.FootprintLoad('/usr/share/kicad/footprints/MountingHole.pretty','MountingHole_3.2mm_M3')
    fp.SetReference('H'+str(i+1));fp.SetPosition(point(x,y));fp.Value().SetVisible(False);fp.Reference().SetVisible(False);board.Add(fp)
for i,(x,y) in enumerate([(24,30),(116,30),(116,110)],1):
    fp=pcb.FootprintLoad('/usr/share/kicad/footprints/Fiducial.pretty','Fiducial_1mm_Mask2mm')
    fp.SetReference('FM'+str(i));fp.SetPosition(point(x,y));fp.Value().SetVisible(False);fp.Reference().SetVisible(False)
    fp.SetAttributes(fp.GetAttributes()|pcb.FP_EXCLUDE_FROM_BOM|pcb.FP_EXCLUDE_FROM_POS_FILES);board.Add(fp)
for a,b in [((20,20),(120,20)),((120,20),(120,120)),((120,120),(20,120)),((20,120),(20,20))]:
    line=pcb.PCB_SHAPE(board);line.SetShape(pcb.SHAPE_T_SEGMENT);line.SetStart(point(*a));line.SetEnd(point(*b));line.SetLayer(pcb.Edge_Cuts);line.SetWidth(mm(.05));board.Add(line)
text('TC IO REV C - 100x100',72,118.2,.9)
text('3.3V ONLY / NO 12V',70,23,1)
text('SENSORS: GND/VCC/AN',70,26,1)
text('DRV LOGIC ONLY',118.5,75,.8).SetTextAngle(pcb.EDA_ANGLE(90,pcb.DEGREES_T))
for i in range(4):text('G/1/2',114,53.2+16*i,.8)
pcb.SaveBoard(str(SRC/(NAME+'.kicad_pcb')),board)
pcb.ExportSpecctraDSN(board,str(SRC/(NAME+'.dsn')))
(SRC/'design_manifest.json').write_text(json.dumps({'name':NAME,'status':'DRAFT_NOT_RELEASED','board_mm':[100,100], 'parts':parts},indent=2))
with (SRC/'BOM_hand_assembly.csv').open('w',newline='') as f:
    w=csv.writer(f,lineterminator="\n");w.writerow(['Reference','Value_or_MPN','Footprint','Quantity','Notes','Populate'])
    for p in parts:w.writerow([p['ref'],p['value'],p['footprint'],int(p['populate']),p['note'],'yes' if p['populate'] else 'no'])
with (SRC/'connections.csv').open('w',newline='') as f:
    w=csv.writer(f,lineterminator="\n");w.writerow(['Reference','Pin','Pin_name','Net'])
    for p in parts:
        for k,n in p['nets'].items():w.writerow([p['ref'],k,p['names'].get(k,k),n or 'NC'])
print('Generated',len(parts),'logical footprints,',sum(p['populate'] for p in parts),'populated SMT parts,',len(nets),'nets')
