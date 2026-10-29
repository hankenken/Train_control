#!/usr/bin/python3
"""Audit/export the small driver draft, not manufacturing files."""
from pathlib import Path
import os,subprocess,csv,json,hashlib,xml.etree.ElementTree as ET,math
import pcbnew as pcb
root=Path(__file__).resolve().parent;s=root/'source';r=root/'reports';v=root/'review';name='TC_DRIVE_REVB'
os.environ.update(XDG_CONFIG_HOME='/tmp/train-kicad/config',XDG_CACHE_HOME='/tmp/train-kicad/cache',XDG_DATA_HOME='/tmp/train-kicad/data')
def run(*args):subprocess.run(['kicad-cli',*map(str,args)],check=True)
run('sch','erc','--format','json','--exit-code-violations','-o',r/'ERC.json',s/(name+'.kicad_sch'))
run('sch','export','netlist','--format','kicadxml','-o',r/'netlist.xml',s/(name+'.kicad_sch'))
run('pcb','drc','--format','json','-o',r/'DRC_UNROUTED.json',s/(name+'.kicad_pcb'))
run('sch','export','pdf','-o',v/'schematic_UNROUTED.pdf',s/(name+'.kicad_sch'))
run('pcb','export','pdf','--layers','F.Fab,F.Silkscreen,Edge.Cuts','--black-and-white','--sketch-pads-on-fab-layers','-o',v/'placement_UNROUTED.pdf',s/(name+'.kicad_pcb'))
run('pcb','export','svg','--layers','F.Cu,F.Fab,F.Silkscreen,Edge.Cuts','--mode-single','--fit-page-to-board','--exclude-drawing-sheet','-o',v/'placement_UNROUTED.svg',s/(name+'.kicad_pcb'))
b=pcb.LoadBoard(str(s/(name+'.kicad_pcb')));actual={(f.GetReference(),pad.GetNumber()):pad.GetNetname() for f in b.GetFootprints() for pad in f.Pads() if pad.GetNetname()}
expected={}
for net in ET.parse(r/'netlist.xml').getroot().findall('./nets/net'):
 n=net.attrib['name'].removeprefix('/')
 for node in net.findall('node'):
  if not node.attrib['ref'].startswith('#'):expected[(node.attrib['ref'],node.attrib['pin'])]=n
assert actual==expected
assert len(b.GetTracks())==0
manifest=json.loads((s/'design_manifest.json').read_text());assert sum(x['populate'] for x in manifest['parts'])==35
orig=json.loads((root.parent/'driver-board/source/design_manifest.json').read_text());old={p['ref']:p for p in orig['parts']};new={p['ref']:p for p in manifest['parts']}
assert old.keys()==new.keys()
for ref in old:
 for k in ['value','nets','populate']:assert old[ref][k]==new[ref][k],(ref,k)
# Actual outline dimensions.
edges=[d for d in b.GetDrawings() if d.GetLayer()==pcb.Edge_Cuts];pts=[p for e in edges for p in [e.GetStart(),e.GetEnd()]]
size=[pcb.ToMM(max(getattr(p,a) for p in pts)-min(getattr(p,a) for p in pts)) for a in ['x','y']];assert size==[60.,45.]
drc=json.loads((r/'DRC_UNROUTED.json').read_text());assert not drc['violations']
# Rectangle-based lower bound on different-net pad spacing, not an IPC current/thermal qualification.
pads=[(f.GetReference()+'.'+pad.GetNumber(),pad) for f in b.GetFootprints() for pad in f.Pads() if pad.GetNetname()]
minimum=(float('inf'),None)
for i,(ar,a) in enumerate(pads):
 for br,bb in pads[i+1:]:
  if a.GetNetname()==bb.GetNetname():continue
  aa=a.GetBoundingBox();bc=bb.GetBoundingBox();dx=max(0,aa.GetLeft()-bc.GetRight(),bc.GetLeft()-aa.GetRight());dy=max(0,aa.GetTop()-bc.GetBottom(),bc.GetTop()-aa.GetBottom());dist=pcb.ToMM(round(math.hypot(dx,dy)))
  if dist<minimum[0]:minimum=(dist,[ar,br])
report={'board':name,'status':'UNROUTED_NOT_FOR_FABRICATION','board_mm':size,'area_mm2':2700,'area_reduction_from_100mm_square_percent':73,'populated_parts':35,'wire_pad_groups':9,'fiducials':3,'mounting':'4 x M2, 2.2mm drill; changed from Rev A M3','electrical_topology_unchanged_from_rev_a':True,'net_assignment_count':len(actual),'schematic_board_net_match':True,'erc_violations':0,'pcb_placement_drc_violations':0,'unconnected_items':len(drc['unconnected_items']),'copper_tracks':0,'minimum_different_net_pad_AABB_spacing_mm':minimum[0],'spacing_pair':minimum[1],'clearance_rule_mm':0.2,'thermal_vias':{'per_ic':8,'drill_mm':0.3,'pad_mm':0.6,'exposed_pad_net':'GND'},'routing_complete':False,'thermal_validation_complete':False,'physical_testing_complete':False,'supplier_sourcing_verified':False,'order_ready':False,'size_is_provisional_until_routing':True,'source_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [s/(name+'.kicad_pcb'),s/(name+'.kicad_sch')]}}
(r/'draft-checks.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
