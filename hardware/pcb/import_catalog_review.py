#!/usr/bin/env python3
"""Import user catalog observations without approving sourcing or altering PCB BOM."""
import csv,io,json,re,hashlib,argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('csv');a=p.parse_args()
src=Path(a.csv);raw=src.read_bytes();text=raw.decode('utf-8-sig')
# First worksheet revision exported literal separators instead of newlines.
if '\n' not in text and '\\r\\n' in text:text=text.replace('\\r\\n','\n')
rows=list(csv.DictReader(io.StringIO(text)))
root=Path(__file__).resolve().parent;out=root/'pcba/catalog';out.mkdir(exist_ok=True)
expected=list(csv.DictReader((root/'pcba/TC_IO_REVC_BOM_DRAFT_NOT_FOR_ORDER.csv').open()))
assert len(rows)==len(expected)==10
assert sum(int(r['Quantity']) for r in rows)==50
assert {r['Designator'] for r in rows}=={r['Designator'] for r in expected}
for r in rows:
 assert not r['LCSC Part #'] or re.fullmatch(r'C[0-9]+',r['LCSC Part #'])
 assert not r['Stock'] or r['Stock'].isdigit()
with (out/'user-observations.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0].keys(),lineterminator='\n');w.writeheader();w.writerows(rows)
report={'source_sha256':hashlib.sha256(raw).hexdigest(),'evidence':'User-entered CSV; not independently verified; observation time unknown','bom_groups':10,'components':50,'groups_with_reported_code':sum(bool(r['LCSC Part #']) for r in rows),'groups_with_reported_stock':sum(bool(r['Stock']) for r in rows),'assembly_confirmed_groups':sum(r['JLCPCB assembly']=='対応を確認' for r in rows),'missing_codes':[r['Designator'] for r in rows if not r['LCSC Part #']],'missing_stock':[r['Designator'] for r in rows if not r['Stock']],'discrepancies':[{'designators':'C1,C2,C3,C4','design_mpn':'C1206C474J5RACTU','reported_alternative':'C1206C474K5RACTU','reported_code':'C2167387','effect':'J=5% versus K=10% initial capacitance tolerance; alternative not adopted'}],'timing_alternative_analysis':{'assumed_coefficient':0.7,'nominal_ms':[49.35,82.25],'passive_upper_ms_5percent':0.7*(150000*1.01+100000*1.2)*470e-9*1.05*1000,'passive_upper_ms_10percent':0.7*(150000*1.01+100000*1.2)*470e-9*1.1*1000,'guaranteed_upper_limit':False,'excluded':'IC coefficient, DC bias, temperature, supply, aging, faults'},'pcb_modified':False,'production_bom_modified':False,'order_ready':False}
(out/'review-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
