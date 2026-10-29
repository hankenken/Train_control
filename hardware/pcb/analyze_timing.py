#!/usr/bin/env python3
"""Sensitivity study, NOT a guaranteed electrical timing model."""
from pathlib import Path
import csv,json
root=Path(__file__).resolve().parent
rows=[]
# These coefficients are sensitivity scenarios, NOT measured or vendor bounds.
for fixed in [120000,130000,150000]:
 for ct in [.05,.10]:
  for k in [.6,.7,.8,.9]:
   upper=k*(fixed*1.01+100000*1.10)*470e-9*(1+ct)*1000
   lower=k*fixed*.99*470e-9*(1-ct)*1000
   rows.append({'fixed_ohms':fixed,'vr_nominal_ohms':100000,'capacitor_nf':470,'capacitor_tolerance':ct,'scenario_k':k,'nominal_min_ms':round(k*fixed*470e-9*1000,6),'nominal_max_ms':round(k*(fixed+100000)*470e-9*1000,6),'passive_lower_ms':round(lower,6),'passive_upper_ms':round(upper,6),'upper_with_cap_temperature_15percent_ms':round(upper*1.15,6),'k_for_100ms_upper':round(.100/((fixed*1.01+100000*1.10)*470e-9*(1+ct)),6)})
out=root/'reports/timing-sensitivity.csv'
with out.open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0].keys(),lineterminator='\n');w.writeheader();w.writerows(rows)
assert len(rows)==24
baseline=next(r for r in rows if r['fixed_ohms']==150000 and r['capacitor_tolerance']==.10 and r['scenario_k']==.7)
assert abs(baseline['passive_upper_ms']-94.63685)<1e-6
(root/'reports/timing-decision.json').write_text(json.dumps({'timer':'CD74HC221M96','datasheet':'TI SCHS166F','supply_v':3.3,'formula_0_7_datasheet_supply_v':4.5,'existing_rc_retained':True,'candidate_fixed_resistors_ohms':[120000,130000,150000],'candidate_k_values_are_guaranteed_bounds':False,'baseline_10percent_cap_k_ceiling_for_100ms':baseline['k_for_100ms_upper'],'x7r_temperature_change_bound':0.15,'baseline_10percent_cap_plus_temperature_ms':baseline['upper_with_cap_temperature_15percent_ms'],'temperature_model':'Conservative multiplicative sensitivity, not a complete vendor guarantee','guaranteed_100ms_limit':False,'decision':'User accepts approximate timing; adopt C2167387 470nF 10% and retain existing R/VR. Calibrate each channel by measurement. No strict 100ms guarantee. Alternative R values remain analysis only.','physical_testing_performed':False},indent=2)+'\n')
print('24 sensitivity scenarios; baseline arithmetic checked')
