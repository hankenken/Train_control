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
NAME = 'TC_IO_REVD_MINI'
parts = []
def uid(s): return str(uuid.uuid5(uuid.NAMESPACE_URL, 'train-control/pcb/revd-mini/'+s))
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
    add('U'+str(2+timer_index),'CD74HC221M96',dip16,nets,(117,53+36*timer_index,0),names,types,
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
    note='RESET_N=pin1,VDD=pin2,VSS=pin3 checked against user-supplied Microchip DS11187F; bench power-ramp testing pending')

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
    add('C'+str(i+1),'470nF_10%_X7R_50V','Capacitor_SMD:C_1206_3216Metric',
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


# Preserve pulse-control parts; the ToF delta below removes four ADC-related parts, leaving 46 SMT parts. Consolidate wire pads.
oldj=next(p for p in parts if p['ref']=='J1')
pi_mapping=[];j1nets={};j1names={};j1types={}
for original,net in sorted(oldj['nets'].items(),key=lambda kv:int(kv[0])):
 if net is None or net in ['MOSI','MISO','SCLK','ADC_CS'] or (net=='GND' and original!='6'):continue
 k=str(len(j1nets)+1);j1nets[k]=net;j1names[k]='PI_PHYS_'+original;j1types[k]=oldj['types'].get(original,'passive')
 pi_mapping.append({'mini_pad':int(k),'pi_physical_pin':int(original),'net':net})
assert len(j1nets)==17
j1nets['18']=None;j1names['18']='NC'
parts=[p for p in parts if not p['ref'].startswith(('J','TP'))]
add('J1','PI_DIRECT_RENUMBERED','TC_Wire:Pads2x09',{int(k):v for k,v in j1nets.items()},(4,14,0),names={int(k):v for k,v in j1names.items()},types={int(k):v for k,v in j1types.items()},note='NEW NUMBERING: 17 used Pi signals plus NC18, see pi-wiring.csv. NOT a 40-pin Pi connector.')
add('J2','SENSOR_BUS','TC_Wire:Pads2x05',{1:'GND',2:'SENSOR_3V3',**{i+3:f'AN{i}' for i in range(8)}},(13,3.5,0),note='1 GND,2 SENSOR_3V3,3..10 ADC CH0..7. New bus replaces individual sensor pad groups.')
add('J3','DRIVER_BUS','TC_Wire:Pads2x05',{1:'GND',**{i*2+j+2:channels[i]+'_IN'+str(j+1) for i in range(4) for j in range(2)},10:None},(51,14,0),note='1 GND,2..9 channel IN1/IN2 pairs;10 NC. No 12V here.')
add('J4','I2C_BUS','TC_Wire:Pads2x02',{1:'GND',2:'+3V3',3:'SDA',4:'SCL'},(51,29,0))
add('JP1','SENSOR_POWER_LINK','TC_Wire:Pads1x02',{1:'+3V3',2:'SENSOR_3V3'},(5,7,0),note='No connector. Bridge only after sensor current check.')
for p in parts:
 if p['ref']=='JP1':p['footprint']='TC_Wire:Pads1x02'
add('TP1','TEST_BUS','TC_Wire:Probe1x07',{1:'GND',2:'CLEAR_N',3:'POWER_GOOD',**{i+4:channels[i]+'_Q' for i in range(4)}},(20,42,0))
placements={'J1':(4,14,0),'J2':(13,3.5,0),'J3':(51,14,0),'J4':(51,29,0),'JP1':(5,7,0),'TP1':(20,42,0),
'U1':(15,20,0),'U2':(29,20,0),'U3':(43,20,0),'U6':(15,34,0),'U4':(29,34,0),'U5':(43,34,0),'U7':(10,41,0),
'VR1':(23,5,0),'VR2':(31,5,0),'VR3':(39,5,0),'VR4':(47,5,0),
'C1':(35,16,90),'R1':(37.5,16,90),'C2':(35,23,90),'R2':(37.5,23,90),'C3':(48.4,16,90),'R3':(48.4,20,90),'C4':(49,24,90),'R4':(52,25,90),
'C5':(20.5,15.5,0),'C6':(31.5,12,0),'C7':(46,12,0),'C8':(32,27,0),'C9':(46,27,0),'C10':(18,27,0),'C11':(14,41,0),'C12':(20,13.1,0),'C13':(8.5,10,0),'R5':(9.5,18,90)}
for i in range(9):placements['R'+str(i+6)]=(22,19+2.4*i,0)
for i in range(7):placements['R'+str(i+15)]=(36,26.5+2.2*i,0)
for i,xy in enumerate([(9.5,36),(9.5,38.3),(18.5,7),(18.5,9.2),(18.5,11.4)],22):placements['R'+str(i)]=(*xy,0)
# ToF revision: no ADC, SPI, analog ports or sensor-power bridge.
parts=[p for p in parts if p['ref'] not in ['U1','R5','C5','C12','J2','JP1']]
placements.update({'J1':(4,12,0),'J3':(46,12,0),'J4':(7,3.5,0),'TP1':(17,38,0),
'U2':(25,18,0),'U3':(39,18,0),'U6':(11,18,0),'U4':(25,32,0),'U5':(39,32,0),'U7':(11,33,0),
'VR1':(19,5,0),'VR2':(27,5,0),'VR3':(35,5,0),'VR4':(42,5,0),
'C1':(31,14,90),'R1':(33.5,14,90),'C2':(31,21,90),'R2':(33.5,21,90),
'C3':(44,14,90),'R3':(44.2,18,90),'C4':(44,22,90),'R4':(47,24,90),
'C6':(27.5,10.5,0),'C7':(42,10.5,0),'C8':(28,25,0),'C9':(42,25.8,0),'C10':(14,25,0),'C11':(14.5,36.2,0),'C13':(12,6,0)})
for i in range(9):placements['R'+str(i+6)]=(18,13+2.4*i,0)
for i in range(7):placements['R'+str(i+15)]=(32,24.5+2.2*i,0)
for i,xy in enumerate([(6,31.5),(6,34),(14.5,9),(14.5,11.2),(14.5,29)],22):placements['R'+str(i)]=(*xy,0)
for p in parts:
 p['pos']=placements[p['ref']];p['populate']=not p['ref'].startswith(('J','TP'))
assert len(parts)==50 and sum(p['populate'] for p in parts)==46
wirelib=SRC/'TC_Wire.pretty';wirelib.mkdir(exist_ok=True)
for name,rows,count in [('Pads2x09',2,18),('Pads2x05',2,10),('Pads2x02',2,4),('Pads1x02',1,2),('Probe1x07',1,7)]:
 s=f'(footprint "{name}" (version 20241229) (generator "pcbnew") (layer "F.Cu") (attr through_hole exclude_from_pos_files exclude_from_bom)\n'
 s+='(property "Reference" "REF**" (at 0 -2) (layer "F.SilkS") (effects (font (size .7 .7))))\n'
 s+=f'(property "Value" "{name}" (at 0 -3) (layer "F.Fab") (effects (font (size .7 .7))))\n'
 for n in range(1,count+1):
  x=(n-1)%2*2 if rows==2 else (n-1)*2;y=(n-1)//2*2 if rows==2 else 0
  if name.startswith('Probe'):s+=f'(pad "{n}" smd circle (at {x} {y}) (size 1.2 1.2) (layers "F.Cu" "F.Mask"))\n'
  else:s+=f'(pad "{n}" thru_hole {"rect" if n==1 else "circle"} (at {x} {y}) (size 1.4 1.4) (drill .8) (layers "*.Cu" "*.Mask"))\n'
 (wirelib/(name+'.kicad_mod')).write_text(s+')\n')
with (SRC/'pi-wiring.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['mini_pad','pi_physical_pin','net'],lineterminator='\n');w.writeheader();w.writerows(pi_mapping)

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
schem+='(title_block (title "TC IO Rev D MINI - UNROUTED DRAFT") (rev "D0-UNROUTED") (comment 1 "50x40mm target; ToF I2C; rewired Pi pads; UNROUTED NOT FOR ORDER"))\n(lib_symbols\n'
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

board=pcb.BOARD();board.SetCopperLayerCount(2)
mm=pcb.FromMM
def pt(x,y):return pcb.VECTOR2I(mm(x),mm(y))
nets={}
for n in sorted({n for p in parts for n in p['nets'].values() if n}):
 net=pcb.NETINFO_ITEM(board,n);board.Add(net);nets[n]=net
for p in parts:
 lib,name=p['footprint'].split(':');folder=str(wirelib) if lib=='TC_Wire' else '/usr/share/kicad/footprints/'+lib+'.pretty'
 f=pcb.FootprintLoad(folder,name);assert f is not None,p['footprint']
 f.SetReference(p['ref']);f.SetValue(p['value']);f.SetFPID(pcb.LIB_ID(lib,name));f.SetPosition(pt(*p['pos'][:2]));f.SetOrientationDegrees(p['pos'][2]);f.Value().SetVisible(False)
 path=pcb.KIID_PATH();path.push_back(pcb.KIID(root_id));path.push_back(pcb.KIID(uid(p['ref'])));f.SetPath(path)
 if not p['populate']:f.SetAttributes(f.GetAttributes()|pcb.FP_DNP|pcb.FP_EXCLUDE_FROM_BOM|pcb.FP_EXCLUDE_FROM_POS_FILES)
 for pad in f.Pads():
  if p['nets'].get(pad.GetNumber()):pad.SetNet(nets[p['nets'][pad.GetNumber()]])
 board.Add(f);f.Reference().SetPosition(pt(*p['pos'][:2]));f.Reference().SetTextAngle(pcb.EDA_ANGLE(0,pcb.DEGREES_T));f.Reference().SetTextSize(pt(.8,.8));f.Reference().SetTextThickness(mm(.12))
 if p['ref']=='U7' or not p['ref'].startswith(('U','VR')):f.Reference().SetLayer(pcb.F_Fab)
for i,(x,y) in enumerate([(2.5,2.5),(47.5,2.5),(2.5,37.5),(47.5,37.5)],1):
 f=pcb.FootprintLoad('/usr/share/kicad/footprints/MountingHole.pretty','MountingHole_2.2mm_M2');f.SetReference('H'+str(i));f.SetPosition(pt(x,y));f.Reference().SetVisible(False);f.Value().SetVisible(False);board.Add(f)
for a,b in [((0,0),(50,0)),((50,0),(50,40)),((50,40),(0,40)),((0,40),(0,0))]:
 line=pcb.PCB_SHAPE(board);line.SetShape(pcb.SHAPE_T_SEGMENT);line.SetStart(pt(*a));line.SetEnd(pt(*b));line.SetLayer(pcb.Edge_Cuts);line.SetWidth(mm(.05));board.Add(line)
for text,x,y in [('IO D TOF',39,38),('PI',4,9),('I2C',7,1),('DRV',46,10)]:
 t=pcb.PCB_TEXT(board);t.SetText(text);t.SetPosition(pt(x,y));t.SetTextSize(pt(.8,.8));t.SetTextThickness(mm(.12));t.SetLayer(pcb.F_SilkS);board.Add(t)
pcb.SaveBoard(str(SRC/(NAME+'.kicad_pcb')),board)
for filename,header,rows in [('BOM_DRAFT.csv',['Reference','MPN_or_value','Footprint','Populate','Notes'],[[p['ref'],p['value'],p['footprint'],p['populate'],p['note']] for p in parts]),('connections.csv',['Reference','Pin','Function','Net'],[[p['ref'],k,p['names'].get(k,k),v] for p in parts for k,v in p['nets'].items()])]:
 with (SRC/filename).open('w',newline='') as f:w=csv.writer(f,lineterminator='\n');w.writerow(header);w.writerows(rows)
(SRC/'design_manifest.json').write_text(json.dumps({'board':NAME,'status':'UNROUTED_NOT_FOR_FABRICATION','board_mm':[50,40],'parts':parts},indent=2)+'\n')
print('IO mini:',len(parts),'logical parts, 46 SMT,50x40mm UNROUTED')
