#!/usr/bin/python3
from pathlib import Path
import os,subprocess,csv,json,hashlib,xml.etree.ElementTree as ET
import pcbnew as pcb
root=Path(__file__).resolve().parent;s=root/'source';r=root/'reports';v=root/'review';name='TC_IO_REVD_MINI'
os.environ.update(XDG_CONFIG_HOME='/tmp/train-kicad/config',XDG_CACHE_HOME='/tmp/train-kicad/cache',XDG_DATA_HOME='/tmp/train-kicad/data')
def run(*args):subprocess.run(['kicad-cli',*map(str,args)],check=True)
run('sch','erc','--format','json','--exit-code-violations','-o',r/'ERC.json',s/(name+'.kicad_sch'))
run('sch','export','netlist','--format','kicadxml','-o',r/'netlist.xml',s/(name+'.kicad_sch'))
run('pcb','drc','--format','json','-o',r/'DRC_UNROUTED.json',s/(name+'.kicad_pcb'))
run('sch','export','pdf','-o',v/'schematic_UNROUTED.pdf',s/(name+'.kicad_sch'))
run('pcb','export','pdf','--layers','F.Fab,F.Silkscreen,Edge.Cuts','--black-and-white','--sketch-pads-on-fab-layers','-o',v/'placement_UNROUTED.pdf',s/(name+'.kicad_pcb'))
b=pcb.LoadBoard(str(s/(name+'.kicad_pcb')))
actual={(f.GetReference(),p.GetNumber()):p.GetNetname() for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()}
expected={}
for net in ET.parse(r/'netlist.xml').getroot().findall('./nets/net'):
 if net.attrib['name'].removeprefix('/').startswith('unconnected-'):continue
 for node in net.findall('node'):expected[(node.attrib['ref'],node.attrib['pin'])]=net.attrib['name'].removeprefix('/')
assert actual==expected
old=pcb.LoadBoard(str(root.parent/'pcb/source/TC_IO_REVC.kicad_pcb'))
oldfp={f.GetReference():f for f in old.GetFootprints()};fps={f.GetReference():f for f in b.GetFootprints()}
kept=[f for f in b.GetFootprints() if f.GetReference().startswith(('U','R','C','VR'))]
assert len(kept)==46
for f in kept:
 ref=f.GetReference();prev=oldfp[ref]
 assert f.GetValue()==prev.GetValue() and f.GetFPID().GetLibItemName()==prev.GetFPID().GetLibItemName()
 assert {p.GetNumber():p.GetNetname() for p in f.Pads()}=={p.GetNumber():p.GetNetname() for p in prev.Pads()}
assert set(oldfp)-set(fps)=={'U1','R5','C5','C12','J2','J5','J6','J7','J8','J9','J10','J11','J12','J13','J14','JP1','TP2','TP3','TP4','TP5','TP6','FM1','FM2','FM3'}
pi=list(csv.DictReader((s/'pi-wiring.csv').open()));assert len(pi)==17
assert {x['net'] for x in pi}=={'+3V3','GND','SDA','SCL','ARM',*[ch+'_'+n for ch in ['UP_OUT','UP_IN','LOW_OUT','LOW_IN'] for n in ['P','N','TRIG']]}
assert not {'MOSI','MISO','SCLK','ADC_CS','SENSOR_3V3'}.intersection(actual.values())
drc=json.loads((r/'DRC_UNROUTED.json').read_text());assert not drc['violations']
assert len(b.GetTracks())==0
edges=list(b.GetDrawings());coords=[p for e in edges if isinstance(e,pcb.PCB_SHAPE) and e.GetLayer()==pcb.Edge_Cuts for p in [e.GetStart(),e.GetEnd()]]
size=[pcb.ToMM(max(getattr(p,a) for p in coords)-min(getattr(p,a) for p in coords)) for a in ['x','y']];assert size==[50,40]
report={'board':name,'status':'UNROUTED_NOT_FOR_FABRICATION','board_mm':size,'area_reduction_from_100_square_percent':80,'parts_populated':46,'retained_smt_net_values_unchanged':True,'adc_removed_refs':['U1','R5','C5','C12'],'pi_used_pads':17,'pi_nc_pad':18,'erc_violations':0,'placement_drc_violations':0,'net_assignment_count':len(actual),'schematic_board_net_match':True,'unconnected_items':len(drc['unconnected_items']),'copper_tracks':0,'order_ready':False,'tof_software_implemented':False,'source_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [s/(name+'.kicad_sch'),s/(name+'.kicad_pcb')]}}
(r/'draft-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print('IO MINI: 46 retained SMT nets/values match;17 Pi used pads;50x40mm; ERC/placement DRC0; UNROUTED')
