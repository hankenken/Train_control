#!/usr/bin/python3
"""Export/audit the NEW unrouted drafts; never export manufacturing Gerbers."""
from pathlib import Path
import os,subprocess,csv,json,hashlib,xml.etree.ElementTree as ET
import pcbnew as pcb
root=Path(__file__).resolve().parent
os.environ.update(XDG_CONFIG_HOME='/tmp/train-kicad/config',XDG_CACHE_HOME='/tmp/train-kicad/cache',XDG_DATA_HOME='/tmp/train-kicad/data')
for folder,name,count in [('driver-board','TC_DRIVE_REVA',35),('sensor-buffer','TC_SENSOR_BUFFER_REVA',21)]:
 p=root/folder;s=p/'source';r=p/'reports';v=p/'review'
 def run(*args):subprocess.run(['kicad-cli',*map(str,args)],check=True)
 run('sch','erc','--format','json','--exit-code-violations','-o',r/'ERC.json',s/(name+'.kicad_sch'))
 run('sch','export','netlist','--format','kicadxml','-o',r/'netlist.xml',s/(name+'.kicad_sch'))
 run('pcb','drc','--format','json','-o',r/'DRC_UNROUTED.json',s/(name+'.kicad_pcb'))
 run('sch','export','pdf','-o',v/'schematic_UNROUTED.pdf',s/(name+'.kicad_sch'))
 run('pcb','export','pdf','--layers','F.Fab,F.Silkscreen,Edge.Cuts','--black-and-white','--sketch-pads-on-fab-layers','-o',v/'placement_UNROUTED.pdf',s/(name+'.kicad_pcb'))
 b=pcb.LoadBoard(str(s/(name+'.kicad_pcb')))
 actual={(f.GetReference(),pad.GetNumber()):pad.GetNetname() for f in b.GetFootprints() for pad in f.Pads() if pad.GetNetname()}
 expected={}
 for net in ET.parse(r/'netlist.xml').getroot().findall('./nets/net'):
  n=net.attrib['name'].removeprefix('/')
  for node in net.findall('node'):
   if not node.attrib['ref'].startswith('#'):expected[(node.attrib['ref'],node.attrib['pin'])]=n
 assert actual==expected,(folder,'schematic/board pin mismatch')
 assert len(b.GetTracks())==0
 rows=list(csv.DictReader((s/'BOM_DRAFT.csv').open()));assert sum(x['Populate']=='True' for x in rows)==count
 drc=json.loads((r/'DRC_UNROUTED.json').read_text())
 report={'board':name,'status':'UNROUTED_NOT_FOR_FABRICATION','populated_parts':count,'board_mm':[100,100],'net_assignment_count':len(actual),'schematic_board_net_match':True,'erc_violations':0,'pcb_drc_violations':len(drc['violations']),'unconnected_items':len(drc['unconnected_items']),'copper_tracks':0,'routing_complete':False,'thermal_validation_complete':False,'physical_testing_complete':False,'supplier_sourcing_verified':False,'order_ready':False,'source_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [s/(name+'.kicad_pcb'),s/(name+'.kicad_sch')]}}
 (r/'draft-checks.json').write_text(json.dumps(report,indent=2)+'\n')
 print(folder,report['net_assignment_count'],'pin assignments match; DRC',report['pcb_drc_violations'],'unconnected',report['unconnected_items'])
