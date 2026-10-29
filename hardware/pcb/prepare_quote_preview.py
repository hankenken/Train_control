#!/usr/bin/env python3
"""Create minimal supplier-import files for preview, never approve an order."""
from pathlib import Path
import csv,json,re,math,hashlib,zipfile,io
root=Path(__file__).resolve().parent
bom=list(csv.DictReader((root/'pcba/TC_IO_REVC_BOM_DRAFT_NOT_FOR_ORDER.csv').open()))
cpl=list(csv.DictReader((root/'pcba/TC_IO_REVC_CPL_DRAFT_NOT_FOR_ORDER.csv').open()))
refs=[s.strip() for r in bom for s in r['Designator'].split(',')]
assert len(bom)==10 and len(refs)==len(set(refs))==50
assert set(refs)=={r['Designator'] for r in cpl} and len(cpl)==50
assert sum(int(r['Quantity']) for r in bom)==50
assert all(re.fullmatch(r'C[0-9]+',r['LCSC Part #']) for r in bom)
assert all(r['Layer']=='Top' and all(math.isfinite(float(r[k].removesuffix('mm'))) for k in ['Mid X','Mid Y','Rotation']) for r in cpl)
release=json.loads((root/'reports/release-checks.json').read_text())
assert release['size_mm']==[100.0,100.0] and not release['pcba_order_ready']
for n,h in release['source_sha256'].items():assert hashlib.sha256((root/'source'/n).read_bytes()).hexdigest()==h
b=io.StringIO(newline='');w=csv.writer(b,lineterminator='\n')
w.writerow(['Comment','Designator','Footprint','LCSC Part #'])
for r in bom:w.writerow([r['Manufacturer Part Number'],r['Designator'],r['Footprint'],r['LCSC Part #']])
files={'BOM_PREVIEW_ONLY.csv':b.getvalue().encode('utf-8-sig'),'CPL_PREVIEW_ONLY.csv':(root/'pcba/TC_IO_REVC_CPL_DRAFT_NOT_FOR_ORDER.csv').read_bytes(),'TC_IO_REVC_JLCPCB_prototype.zip':(root/'TC_IO_REVC_JLCPCB_prototype.zip').read_bytes(),'README_JA.md':(root/'pcba/jlcpcb-preview-guide.md').read_bytes(),'IC_VR_pin1_review.pdf':(root/'review/IC_VR_pin1_review.pdf').read_bytes()}
manifest={'purpose':'JLCPCB quote and placement preview ONLY; not approved for purchase','bom_groups':10,'parts_per_board':50,'side':'Top','board_mm':[100,100],'strict_100ms_required':False,'assembly_eligibility_verified':False,'supplier_rotation_verified':False,'supplier_pickup_centers_verified':False,'hashes':{n:hashlib.sha256(v).hexdigest() for n,v in files.items()}}
files['PREVIEW_MANIFEST.json']=(json.dumps(manifest,indent=2)+'\n').encode()
archive=root/'TC_IO_REVC_JLCPCB_QUOTE_PREVIEW_ONLY.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for n,v in files.items():z.writestr(n,v)
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 for n,h in manifest['hashes'].items():assert hashlib.sha256(z.read(n)).hexdigest()==h
(root/'reports/quote-preview.json').write_text(json.dumps({**manifest,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()},indent=2)+'\n')
print('Preview bundle verified: 10 BOM groups, 50 Top-side CPL rows, 6 files; NOT FOR ORDER')
