#!/usr/bin/python3
"""Export review-only PCBA data. Never claim catalog/rotation validation.

Uses KiCad system Python. Catalog references and package rotations must be
confirmed before converting these drafts into order files.
"""
from pathlib import Path
from collections import defaultdict
import csv,json,hashlib
import pcbnew as pcb

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'pcba';OUT.mkdir(exist_ok=True)
NAME='TC_IO_REVC'
all_rows=list(csv.DictReader((ROOT/'source/BOM_hand_assembly.csv').open(newline='')))
rows=[r for r in all_rows if r['Populate']=='yes']
omitted=[r for r in all_rows if r['Populate']=='no']
board=pcb.LoadBoard(str(ROOT/'source'/(NAME+'.kicad_pcb')))
lookup={fp.GetReference():fp for fp in board.GetFootprints()}
assert len(all_rows)==71 and len(rows)==50 and len(omitted)==21
assert all(lookup[r['Reference']].GetAttributes() & pcb.FP_SMD for r in rows)
def catalog_identity(row):
    ref=row['Reference']
    if ref=='U1':return row['Value_or_MPN'],'Microchip',row['Value_or_MPN']
    if ref in ['U2','U3','U4','U5','U6']:return row['Value_or_MPN'],'Texas Instruments',row['Value_or_MPN']
    if ref=='U7':return row['Value_or_MPN'],'Microchip',row['Value_or_MPN']
    if ref.startswith('VR'):return row['Value_or_MPN'],'Bourns',row['Value_or_MPN']
    if ref.startswith('R'):
        return row['Value_or_MPN'],'Yageo','RC0805FR-07150KL' if ref in ['R1','R2','R3','R4'] else 'RC0805FR-0710KL'
    if ref.startswith('C'):
        number=int(ref[1:]);mpn='C1206C474J5RACTU' if number<=4 else 'C0805C104K5RACTU' if number<=12 else 'C1206C106K3RACTU'
        return row['Value_or_MPN'],'KEMET',mpn
    return row['Value_or_MPN'],'',''
# Keep user observations distinct from independent manufacturer verification.
observations=list(csv.DictReader((OUT/'catalog/user-observations.csv').open()))
observed_by_mpn={r['Manufacturer Part Number']:r for r in observations}
groups=defaultdict(list)
for row in rows:
    comment,mfr,mpn=catalog_identity(row)
    groups[(comment,row['Footprint'],mfr,mpn)].append(row)
bom=OUT/(NAME+'_BOM_DRAFT_NOT_FOR_ORDER.csv')
with bom.open('w',newline='') as f:
    w=csv.writer(f,lineterminator="\n");w.writerow(['Comment','Designator','Footprint','LCSC Part #','Manufacturer','Manufacturer Part Number','Quantity','Status'])
    for (comment,footprint,mfr,mpn),items in groups.items():
        observation=observed_by_mpn.get(mpn)
        code=''
        sourcing_status='CANDIDATE ONLY: LCSC listing, datasheet, stock and assembly eligibility not verified'
        if mpn=='CD74HC221M96':
            code='C133954'
            sourcing_status='User screenshot matches MPN, SOIC-16 and LCSC code; stock shown 1761; JLCPCB eligibility and rotation pending'
        elif observation and mpn!='C1206C474J5RACTU':
            code=observation['LCSC Part #']
            sourcing_status='USER CSV ONLY: reported code; MPN/package/datasheet and JLCPCB eligibility need verification'
        elif mpn=='C1206C474J5RACTU':
            sourcing_status='HOLD: user reported C2167387 for K (10%) alternative, not the J (5%) design; do not assign code'
        w.writerow([comment,','.join(r['Reference'] for r in items),footprint,code,mfr,mpn,
                    sum(int(r['Quantity']) for r in items),sourcing_status])

# Candidate coordinates use the standard SMT footprint origin, in the SAME
# absolute coordinate system as the Gerbers, with Y negated. Supplier pickup
# center and rotation must be checked. Unpopulated wire groups are excluded.
cpl=OUT/(NAME+'_CPL_DRAFT_NOT_FOR_ORDER.csv')
placement=OUT/'placement-review.csv'
with cpl.open('w',newline='') as f, placement.open('w',newline='') as review:
    w=csv.writer(f,lineterminator="\n");w.writerow(['Designator','Mid X','Mid Y','Layer','Rotation'])
    rw=csv.writer(review,lineterminator="\n");rw.writerow(['Designator','Anchor X mm','Anchor Y mm','Pad-centroid X mm','Pad-centroid Y mm','KiCad Rotation deg','Footprint','Review'])
    for row in rows:
        ref=row['Reference'];fp=lookup[ref];pads=list(fp.Pads())
        px=sum(pcb.ToMM(p.GetPosition().x) for p in pads)/len(pads)
        py=sum(pcb.ToMM(p.GetPosition().y) for p in pads)/len(pads)
        x=pcb.ToMM(fp.GetPosition().x);y=pcb.ToMM(fp.GetPosition().y)
        rotation=fp.GetOrientationDegrees()%360
        w.writerow([ref,f'{x:.4f}mm',f'{-y:.4f}mm','Top',f'{rotation:.1f}'])
        rw.writerow([ref,f'{x:.4f}',f'{y:.4f}',f'{px:.4f}',f'{py:.4f}',rotation,row['Footprint'],
                     'CPL uses SMT footprint origin; supplier pickup point and rotation still need verification'])
with (OUT/'excluded-wire-pads.csv').open('w',newline='') as f:
    w=csv.writer(f,lineterminator="\n");w.writerow(['Designator','Reason'])
    for r in omitted:w.writerow([r['Reference'],'Wire/test pads only, NO connector or header component to be fitted'])
status={
 'board':NAME,'status':'BLOCKED_NOT_FOR_PCBA_ORDER',
 'intended_scope':'50 SMT parts including all ICs, resistors, capacitors and four VRs; connectors omitted',
 'assembly_technology':'Top-side SMT only; 21 plated wire/test-pad groups carry no components',
 'board_source_sha256':hashlib.sha256((ROOT/'source'/(NAME+'.kicad_pcb')).read_bytes()).hexdigest(),
 'component_count':50,'bom_designator_count':50,'cpl_rows':50,'omitted_wire_groups':21,
 'catalog_access':'JLCPCB and LCSC HTTPS CONNECT 403 at preparation time',
 'one_shot_part':{'mpn':'CD74HC221M96','lcsc_code':'C133954','evidence':'User screenshot and TI SCHS166F','observed_stock':1761,'jlcpcb_eligibility_verified':False},
 'lcsc_codes_verified':False,'stock_verified':False,'assembly_eligibility_verified':False,
 'pickup_centers_verified':False,'rotations_verified':False,
 'paste_layers_exported':all((ROOT/'manufacturing'/(NAME+s)).exists() for s in ['-F_Paste.gtp','-B_Paste.gbp']),
 'sockets_included':False,
 'blockers':['Verify ALL candidate MPNs against current LCSC listings, stock and JLCPCB assembly eligibility',
             'Fill LCSC codes only after matching manufacturer, MPN and package',
             'Verify datasheets, footprints, pin1, pickup points and rotation per accepted supplier parts',
             'Check timing-MLCC capacitance under DC bias and temperature, and measure all VR ranges'],
}
(OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n')
print('Generated PCBA review drafts:',len(rows),'components;',len(groups),'BOM groups; NOT FOR ORDER')
