#!/usr/bin/env python3
"""Generate a pin-level KiCad CIRCUIT DRAFT. No PCB, Gerber, CPL or sourcing claim."""
from pathlib import Path
import csv,json,uuid
ROOT=Path(__file__).resolve().parent
SRC=ROOT/'source'; SRC.mkdir(exist_ok=True)
NAME='TC_I2C_DRIVE_REVA';parts=[]
def uid(s):return str(uuid.uuid5(uuid.NAMESPACE_URL,'train-control/i2c-drive/a0/'+s))
def q(s):return json.dumps(str(s),ensure_ascii=False)
def add(ref,value,fp,nets,names=None,types=None,note='',populate=True):
    p=dict(ref=ref,value=value,footprint=fp,nets={str(k):v for k,v in nets.items()},names={str(k):v for k,v in (names or {}).items()},types={str(k):v for k,v in (types or {}).items()},populate=populate,note=note)
    parts.append(p);return p
r='Resistor_SMD:R_0805_2012Metric';c='Capacitor_SMD:C_0805_2012Metric'
add('J1','LATTEPANDA_CONTROL_WIRES','',{1:'GND',2:'+5V_LOGIC',3:'SDA',4:'SCL',5:'SLEEP_REQ_D4',6:'TRIG_D5',7:'PERMIT_D6',8:'FAULT_N_D7',9:'VM_ADC_A0'},
    {1:'GND',2:'5V',3:'D2_SDA',4:'D3_SCL',5:'D4',6:'D5',7:'D6',8:'D7',9:'A0'},
    {1:'power_out',2:'power_out',3:'bidirectional',4:'output',5:'output',6:'output',7:'input',8:'input',9:'input'},populate=False,note='Wire holes only; board physical header mapping must be checked. Never connect VM to logic 5V.')
add('J2','12V_AFTER_EXTERNAL_FUSE_AND_LATCHING_STOP','',{1:'VIN_12V',2:'GND'},types={1:'power_out'},populate=False,note='External 2A fuse initial candidate; verify fault clearing vs wiring and supply current limit.')
add('D1','SS34_CANDIDATE','Diode_SMD:D_SMA',{1:'VM',2:'VIN_12V'},{1:'K',2:'A'},note='Series reverse polarity protection; forward loss and surge rating need selected datasheet.')
add('D2','SMBJ18A_CANDIDATE','Diode_SMD:D_SMB',{1:'VM',2:'GND'},{1:'K',2:'A'},note='Regeneration clamp. Inductive energy and overshoot not yet measured; no generic flyback diode across bipolar load.')
add('C1','470uF_35V_BULK_CANDIDATE','Capacitor_SMD:CP_Elec_10x10.5',{1:'VM',2:'GND'},{1:'PLUS',2:'MINUS'},note='Specific manufacturer/ESR/ripple ratings unresolved.')
for i in range(4):
    ch=f'CH{i}';u='U'+str(i+1)
    nets={1:ch+'_IPROPI',2:None,3:None,4:'FAULT_N_D7',5:'VM',6:ch+'_OUT1',7:'GND',8:ch+'_OUT2',9:'GND' if i<2 else '+5V_LOGIC',10:'GND' if i%2==0 else '+5V_LOGIC',11:'NSLEEP_ALL',12:'GND',13:'GND',14:'SDA',15:'SCL',16:ch+'_VREF',17:'GND'}
    names=dict(enumerate(['IPROPI','RSVD_NC','RSVD_NC','nFAULT','VM','OUT1','GND','OUT2','A1','A0','nSLEEP','IN2','IN1','SDA','SCL','VREF','EP_GND'],1))
    types={1:'passive',4:'open_collector',5:'power_in',6:'output',7:'power_in',8:'output',9:'input',10:'input',11:'input',12:'input',13:'input',14:'bidirectional',15:'input',16:'input',17:'power_in'}
    add(u,'DRV8235RTER','Package_DFN_QFN:WQFN-16-1EP_3x3mm_P0.5mm_EP1.68x1.68mm',nets,names,types,note=f'TI SLVSHO3. 7bit address {["0x30","0x32","0x36","0x38"][i]}. RTE0016C exact land/thermal via review required, not old Texas_RTE footprint with smaller EP.')
    add('R'+str(i+1),'1.69k_1%',r,{1:ch+'_IPROPI',2:'GND'},note='Itrip nominal 1.183A with internal3V; not forced current. No direct electrical relation to old DRV8871 ILIM.')
    add('C'+str(i+2),'100nF_50V_X7R',c,{1:'VM',2:'GND'},note='Place immediately VM to GND; no long common trace.')
    add('C'+str(i+6),'100nF_16V_X7R',c,{1:ch+'_VREF',2:'GND'},note='VREF input bypass, internal3V selected in CONFIG3. Never tie to5V.')
    add('J'+str(i+3),f'TURNOUT_{i}_BLUE_WHITE_WIRES','',{1:ch+'_OUT1',2:ch+'_OUT2'},{1:'BLUE_CANDIDATE',2:'WHITE_CANDIDATE'},populate=False,note='Blue/white to physical route P/N must be measured; no connector installed.')
add('U5','CD74HC221M96','Package_SO:SOIC-16_3.9x9.9mm_P1.27mm',
    {1:'GND',2:'TRIG_D5',3:'POWER_GOOD',4:None,5:None,6:None,7:None,8:'GND',9:'GND',10:'GND',11:'GND',12:None,13:'PERMIT_D6',14:'TIMER_CX',15:'TIMER_RXCX',16:'+5V_LOGIC'},
    {1:'1A',2:'1B',3:'1RESET_N',4:'1Q_N',5:'2Q',6:'2CX_UNUSED',7:'2RXCX_UNUSED',8:'GND',9:'2A',10:'2B',11:'2RESET_N',12:'2Q_N',13:'1Q',14:'1CX',15:'1RXCX',16:'VCC'},
    {1:'input',2:'input',3:'input',4:'output',5:'output',8:'power_in',9:'input',10:'input',11:'input',12:'output',13:'output',16:'power_in'},
    note='Non-retriggerable one-shot. Unused half reset low and inputs low. Cext is between14 and15, NOT toGND. Existing LCSC C133954 evidence is historical, not fresh availability.')
add('R5','620k_1%',r,{1:'+5V_LOGIC',2:'TIMER_RXCX'},note='0.7RC at4.5V with470nF gives204ms nominal; NOT guaranteed worst-case bound.')
add('C10','470nF_50V_X7R_10%','Capacitor_SMD:C_1206_3216Metric',{1:'TIMER_CX',2:'TIMER_RXCX'},note='C2167387 historical selected KEMET; fresh stock unverified. Timer tolerance and supply/temp must be measured.')
add('U6','SN74HC08DR','Package_SO:SOIC-14_3.9x8.7mm_P1.27mm',
    {1:'SLEEP_REQ_D4',2:'PERMIT_D6',3:'SLEEP_PRE',4:'SLEEP_PRE',5:'POWER_GOOD',6:'SLEEP_GATED',7:'GND',8:None,9:'GND',10:'GND',11:None,12:'GND',13:'GND',14:'+5V_LOGIC'},
    {1:'1A',2:'1B',3:'1Y',4:'2A',5:'2B',6:'2Y',7:'GND',8:'3Y_NC',9:'3A',10:'3B',11:'4Y_NC',12:'4A',13:'4B',14:'VCC'},
    {1:'input',2:'input',3:'output',4:'input',5:'input',6:'output',7:'power_in',8:'output',9:'input',10:'input',11:'output',12:'input',13:'input',14:'power_in'},note='nSLEEP = D4 AND one-shotQ AND powergood; pinout TI HC08 SOIC14, unused inputs grounded.')
add('U7','MCP100T-450I/TT_CANDIDATE','Package_TO_SOT_SMD:SOT-23',{1:'POWER_GOOD',2:'+5V_LOGIC',3:'GND'},
    {1:'RESET_N',2:'VDD',3:'VSS'},{1:'output',2:'power_in',3:'power_in'},note='DS11187F SOT23 pinout1reset2VDD3VSS. 4.5V grade proposed for5V; not previous3.0V grade. Exact ordercode/threshold/supply range pending purchasing review.')
for ref in ['C11','C12','C13']:
    add(ref,'100nF_16V_X7R',c,{1:'+5V_LOGIC',2:'GND'},note='One at each U5/U6/U7.')
for ref,net,value in [('R6','SDA','4.7k_1%'),('R7','SCL','4.7k_1%'),('R8','FAULT_N_D7','10k_1%')]:
    add(ref,value,r,{1:'+5V_LOGIC',2:net},note='One shared pullup. Account for pullups already on host/bus.')
for ref,net in [('R9','SLEEP_REQ_D4'),('R10','TRIG_D5'),('R11','PERMIT_D6'),('R12','NSLEEP_ALL')]:
    add(ref,'10k_1%',r,{1:net,2:'GND'},note='External default-low; no floating permit/bypass jumper.')
add('R13','100R_1%',r,{1:'SLEEP_GATED',2:'NSLEEP_ALL'})
add('R14','100k_1%',r,{1:'VM',2:'VM_DIV'})
add('R15','10k_1%',r,{1:'VM_DIV',2:'GND'})
add('Q1','BSS138_CANDIDATE','Package_TO_SOT_SMD:SOT-23',{1:'+5V_LOGIC',2:'VM_ADC_A0',3:'VM_DIV'},
    {1:'GATE',2:'SOURCE',3:'DRAIN'},note='Analog isolation when logic power is OFF: body diode anode=A0, cathode=VM_DIV. Source/drain orientation critical. 12V-only prototype, measure transfer. Exact manufacturer datasheet pending.')
add('R16','1M_1%',r,{1:'VM_ADC_A0',2:'GND'},note='ADC side discharge; effective VM divider ratio about11.1 when Q1ON.')
add('R17','100k_1%',r,{1:'+5V_LOGIC',2:'GND'},note='Discharge Q1 gate/logic rail when host loses power.')
add('C14','10nF_16V_X7R',c,{1:'VM_ADC_A0',2:'GND'},note='ADC filter; cold detection requires100ms low AFTER MCUboot.')
add('R18','2.2k_0.5W_BLEED','Resistor_SMD:R_2010_5025Metric',{1:'VM',2:'GND'},note='Discharges470uF: tau about1.03s, nominal12V to0.27V about3.9s. Verify actual cold threshold; no automatic timed assumption.')
add('#FLG01','PWR_FLAG_VM','',{1:'VM'},types={1:'power_out'},populate=False,note='Electrical annotation only, supply throughD1.')

# Generic pin-level symbols deliberately expose every pin and every no-connect.
(SRC/(NAME+'.kicad_pro')).write_text(json.dumps({'meta':{'filename':NAME+'.kicad_pro','version':1}},indent=2)+'\n')
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
schem+='(title_block (title "TC I2C DRIVE Rev A - CIRCUIT DRAFT ONLY") (rev "A0-CIRCUIT") (comment 1 "12V prototype. Native I2C. No PCB routes / NO FABRICATION FILES."))\n(lib_symbols\n'
defs=[]; library=[]
for p in parts:
    d,pins,h=symdef(p); schem+=d+'\n'; defs.append((pins,h)); library.append(d.replace('"TC:'+p['ref']+'"',q(p['ref']),1))
schem+=')\n'
for i,p in enumerate(parts):
    pins,h=defs[i]; x=50.8+(i%6)*129.54; y=50.8+(i//6)*60.96
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

for filename, header, rows in [
 ('BOM_DRAFT.csv',['Reference','MPN_or_value','Footprint_candidate','Populate','Notes'],[[p['ref'],p['value'],p['footprint'],p['populate'],p['note']] for p in parts]),
 ('connections.csv',['Reference','Pin','Function','Net'],[[p['ref'],k,p['names'].get(k,k),v] for p in parts for k,v in p['nets'].items()])]:
 with (SRC/filename).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f,lineterminator='\n');w.writerow(header);w.writerows(rows)
(SRC/'design_manifest.json').write_text(json.dumps({'status':'CIRCUIT_DRAFT_NO_PCB_NO_FABRICATION','target_board_mm':[50,40],'target_is_not_validated_layout':True,'parts':parts},indent=2)+'\n')
print(len(parts),'logical elements;',sum(p['populate'] for p in parts),'SMT candidates; NO PCB or production files')
