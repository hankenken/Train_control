#!/usr/bin/env python3
"""Bundle current review files without approving an order."""
from pathlib import Path
import zipfile,json,hashlib,csv
root=Path(__file__).resolve().parent
bom=list(csv.DictReader((root/'pcba/TC_IO_REVC_BOM_DRAFT_NOT_FOR_ORDER.csv').open()))
assert len(bom)==10 and sum(int(r['Quantity']) for r in bom)==50
cap=next(r for r in bom if r['Designator']=='C1,C2,C3,C4');assert cap['LCSC Part #']=='C2167387' and cap['Manufacturer Part Number']=='C1206C474K5RACTU'
assert next(r for r in bom if r['Designator']=='U2,U3')['LCSC Part #']=='C133954'
release=json.loads((root/'reports/release-checks.json').read_text())
for n,h in release['source_sha256'].items():assert hashlib.sha256((root/'source'/n).read_bytes()).hexdigest()==h
for n,h in release['fabrication_sha256'].items():assert hashlib.sha256((root/'manufacturing'/n).read_bytes()).hexdigest()==h
assert not json.loads((root/'pcba/status.json').read_text())['assembly_eligibility_verified']
review=root/'TC_IO_REVC_PCBA_REVIEW_NOT_FOR_ORDER.zip'
paths=[x for x in (root/'pcba').rglob('*') if x.is_file()]+list((root/'reports').glob('*.json'))+list((root/'reports').glob('*.csv'))+[root/'reports/netlist.xml',root/'README.md',root/'TC_IO_REVC_JLCPCB_prototype.zip',root/'review/TC_IO_REVC_documents.pdf']
with zipfile.ZipFile(review,'w',zipfile.ZIP_DEFLATED) as z:
 for f in sorted(set(paths)):z.write(f,f.relative_to(root))
package=root/'TC_IO_REVC_design_package.zip'
with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
 for f in sorted(root.rglob('*')):
  if not f.is_file() or f==package or '__pycache__' in f.parts or f.suffix in ['.pyc','.prl'] or 'backups' in f.parts:continue
  z.write(f,f.relative_to(root))
for f in [review,package]:
 with zipfile.ZipFile(f) as z:assert z.testzip() is None
print('Source/fab hashes, BOM selection, quantities and archive CRCs verified; NOT FOR ORDER')
