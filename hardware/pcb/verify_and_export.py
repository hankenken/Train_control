#!/usr/bin/python3
"""Validate the routed prototype, then export bare-PCB manufacturing files.
Requires KiCad 9 system Python. Does not order or upload anything.
"""
from pathlib import Path
import csv, hashlib, json, os, subprocess, xml.etree.ElementTree as ET, zipfile
import pcbnew as pcb

ROOT=Path(__file__).resolve().parent
SRC=ROOT/'source'; REPORT=ROOT/'reports'; FAB=ROOT/'manufacturing'; REVIEW=ROOT/'review'
for path in [REPORT,FAB,REVIEW]:path.mkdir(exist_ok=True)
NAME='TC_IO_REVB'; BOARD=SRC/(NAME+'.kicad_pcb'); SCH=SRC/(NAME+'.kicad_sch')
def run(*args):subprocess.run(['kicad-cli',*map(str,args)],check=True)
run('pcb','drc','--format','json','--exit-code-violations','-o',REPORT/'DRC.json',BOARD)
run('sch','erc','--format','json','--exit-code-violations','-o',REPORT/'ERC.json',SCH)
drc=json.loads((REPORT/'DRC.json').read_text());erc=json.loads((REPORT/'ERC.json').read_text())
assert not drc['violations'] and not drc['unconnected_items']
assert not [v for s in erc['sheets'] for v in s['violations']]
run('sch','export','netlist','--format','kicadxml','-o',REPORT/'netlist.xml',SCH)
xml=ET.parse(REPORT/'netlist.xml').getroot()
expected={}
for net in xml.findall('./nets/net'):
    name=net.attrib['name'].removeprefix('/')
    for node in net.findall('node'):
        if not name.startswith('unconnected-'):expected[(node.attrib['ref'],node.attrib['pin'])]=name
board=pcb.LoadBoard(str(BOARD));actual={}
edges=[item for item in board.GetDrawings() if item.GetLayer()==pcb.Edge_Cuts]
assert len(edges)==4 and all(e.GetShape()==pcb.SHAPE_T_SEGMENT for e in edges)
edge_points=[point for e in edges for point in [e.GetStart(),e.GetEnd()]]
size_mm=[pcb.ToMM(max(getattr(p,axis) for p in edge_points)-min(getattr(p,axis) for p in edge_points)) for axis in ['x','y']]
assert size_mm==[100.0,100.0], size_mm
assert sum(fp.GetReference().startswith('H') for fp in board.GetFootprints())==4
for fp in board.GetFootprints():
    for pad in fp.Pads():
        if pad.GetNetname():actual[(fp.GetReference(),pad.GetNumber())]=pad.GetNetname()
assert actual==expected, {'missing_or_mismatched':[(k,v,actual.get(k)) for k,v in expected.items() if actual.get(k)!=v],
                         'extra':[(k,v) for k,v in actual.items() if k not in expected]}
assert set(actual.values()).isdisjoint({'12V','+12V','VM','COIL'})
assert actual[('U2','13')]=='UP_OUT_Q' and actual[('U2','5')]=='UP_IN_Q'
assert actual[('U7','1')]=='POWER_GOOD' and actual[('U7','2')]=='+3V3' and actual[('U7','3')]=='GND'
for i in range(8):
    assert actual[('U1',str(i+1))]==f'AN{i}'
    assert actual[('J'+str(i+2),'3')]==f'AN{i}'
assert actual[('JP1','1')]=='+3V3' and actual[('JP1','2')]=='SENSOR_3V3'
run('pcb','export','gerbers','-l','F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts',
    '--subtract-soldermask','-o',str(FAB)+'/',BOARD)
run('pcb','export','drill','--format','excellon','--excellon-units','mm','--excellon-separate-th','-o',str(FAB)+'/',BOARD)
# KiCad 9's job file reports the stroke-inclusive outline bounding box.
# Use the actual routed profile centerline dimensions, measured above, so
# metadata agrees with the physical 100 x 100 mm board, not 100.05 mm.
job_path=FAB/(NAME+'-job.gbrjob')
job=json.loads(job_path.read_text())
job['GeneralSpecs']['Size']={'X':size_mm[0],'Y':size_mm[1]}
job['GeneralSpecs']['ProjectId']['Revision']='B0-PROTOTYPE'
job_path.write_text(json.dumps(job,indent=2)+'\n')
run('sch','export','pdf','-o',REVIEW/'schematic.pdf',SCH)
run('pcb','export','pdf','--layers','F.Fab,F.Silkscreen,Edge.Cuts','--sketch-pads-on-fab-layers',
    '-o',REVIEW/'assembly-top.pdf',BOARD)
run('pcb','export','svg','--layers','F.Cu,F.Silkscreen,Edge.Cuts','--mode-single','--fit-page-to-board',
    '--exclude-drawing-sheet','-o',REVIEW/'board-top.svg',BOARD)
svg_path=REVIEW/'board-top.svg'
svg_path.write_text('\n'.join(line.rstrip() for line in svg_path.read_text().splitlines())+'\n')
files=sorted(p for p in FAB.iterdir() if p.suffix.lower() in ['.gtl','.gbl','.gts','.gbs','.gto','.gbo','.gm1','.gbr','.drl','.gbrjob'])
assert {'.gtl','.gbl','.gts','.gbs','.gto','.gbo','.gm1','.drl'} <= {p.suffix.lower() for p in files}
assert sum(p.suffix=='.drl' for p in files)==2
for p in files:
    assert p.stat().st_size>0
    if p.suffix=='.drl':assert 'METRIC' in p.read_text()
    if p.suffix in ['.gtl','.gbl','.gts','.gbs','.gto','.gbo','.gm1']:
        content=p.read_text();assert '%MOMM*%' in content and 'M02*' in content
archive=ROOT/(NAME+'_JLCPCB_prototype.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files:z.write(p,p.name)
manifest={
  'board':NAME,'status':'UNTESTED_PROTOTYPE_NOT_PRODUCTION_QUALIFIED',
  'size_mm':size_mm,'layers':2,'thickness_mm':1.6,'copper_oz':1,'assembly':'bare PCB, hand assembly',
  'included_function':'3.3V logic, 8 ADC channels, 4 pulse gates; separate DRV8871 modules required',
  'drc_violations':0,'unconnected_items':0,'erc_violations':0,'schematic_pcb_netlist_match':True,
  'manufacturer_datasheet_review_complete':False,'physical_testing_complete':False,
  'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [BOARD,SCH,SRC/'TC.kicad_sym']},
  'fabrication_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
  'zip_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
}
(REPORT/'release-checks.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Verified and exported bare-PCB prototype:',archive)
