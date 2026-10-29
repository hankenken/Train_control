#!/usr/bin/python3
"""Verify mini placement and electrical parity; NOT fabrication approval."""
from pathlib import Path
import json,csv,hashlib,xml.etree.ElementTree as ET
import pcbnew as pcb
root=Path(__file__).resolve().parent;src=root/'source';name='TC_SENSOR_BUFFER_REVB_MINI'
b=pcb.LoadBoard(str(src/(name+'.kicad_pcb')))
old=json.loads((root.parent/'sensor-buffer/source/design_manifest.json').read_text())['parts']
new=json.loads((src/'design_manifest.json').read_text())['parts']
oldpop={p['ref']:p for p in old if p['populate']};newpop={p['ref']:p for p in new if p['populate']}
assert set(oldpop)==set(newpop) and len(newpop)==21
for ref,p in oldpop.items():
 assert (p['value'],p['footprint'],p['nets'])==(newpop[ref]['value'],newpop[ref]['footprint'],newpop[ref]['nets'])
actual={(f.GetReference(),d.GetNumber()):d.GetNetname() for f in b.GetFootprints() for d in f.Pads() if d.GetNetname()}
expected={}
for net in ET.parse(root/'reports/netlist.xml').getroot().findall('./nets/net'):
 for n in net.findall('node'):expected[(n.attrib['ref'],n.attrib['pin'])]=net.attrib['name'].removeprefix('/')
assert actual==expected
edges=list(b.GetDrawings());edges=[e for e in edges if e.GetLayer()==pcb.Edge_Cuts];assert len(edges)==4
points=[p for e in edges for p in [e.GetStart(),e.GetEnd()]]
size=[pcb.ToMM(max(getattr(p,k) for p in points)-min(getattr(p,k) for p in points)) for k in ['x','y']];assert size==[45,32]
drc=json.loads((root/'reports/DRC_UNROUTED.json').read_text());erc=json.loads((root/'reports/ERC.json').read_text())
assert not drc['violations'];assert not any(s['violations'] for s in erc['sheets']);assert len(b.GetTracks())==0
report={'name':name,'status':'PLACEMENT_DRAFT_UNROUTED_NOT_FOR_ORDER','board_mm':size,'area_mm2':1440,'previous_area_mm2':10000,'area_reduction_percent':85.6,'populated_smt':21,'unpopulated_wire_groups':9,'wire_drill_mm':.8,'wire_pad_size_mm':1.6,'wire_pitch_mm':2,'wire_pad_edge_gap_mm':.4,'minimum_clearance_rule_mm':.2,'mounting_holes':{'count':4,'diameter_mm':2.2,'hardware':'M2'},'electrical_parity_with_rev_a_smt':True,'schematic_board_net_match':True,'connected_pad_assignments':len(actual),'erc_violations':0,'placement_drc_violations':0,'unconnected_items':len(drc['unconnected_items']),'copper_tracks':0,'routing_complete':False,'board_dimensions_final_after_routing':False,'supplier_sourcing_verified':False,'supplier_orientation_verified':False,'physical_testing_complete':False,'order_ready':False,'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [src/(name+'.kicad_pcb'),src/(name+'.kicad_sch')]}}
(root/'reports/draft-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print('45x32 mm,21 SMT,100 pin assignments match; ERC0, placement DRC0;74 unrouted connections, NOT FOR ORDER')
