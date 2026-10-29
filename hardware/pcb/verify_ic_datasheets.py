#!/usr/bin/python3
"""Compare PCB nets with pin roles transcribed from supplied manufacturer PDFs."""
from pathlib import Path
import json,hashlib
import pcbnew as pcb
root=Path(__file__).resolve().parent
board=root/'source/TC_IO_REVC.kicad_pcb';b=pcb.LoadBoard(str(board))
fps={f.GetReference():f for f in b.GetFootprints()}
expected={'U1':{**{str(i+1):f'AN{i}' for i in range(8)},'9':'GND','10':'ADC_CS','11':'MOSI','12':'MISO','13':'SCLK','14':'GND','15':'+3V3','16':'+3V3'},'U7':{'1':'POWER_GOOD','2':'+3V3','3':'GND'},'U6':{'1':'ARM','2':'POWER_GOOD','3':'CLEAR_N','4':'GND','5':'GND','6':'','7':'GND','8':'','9':'GND','10':'GND','11':'','12':'GND','13':'GND','14':'+3V3'}}
for ref,channels in [('U4',['UP_OUT','UP_IN']),('U5',['LOW_OUT','LOW_IN'])]:
 pins={'7':'GND','14':'+3V3'}
 for n,(a,bb,y) in enumerate([(1,2,3),(4,5,6),(9,10,8),(12,13,11)]):
  ch=channels[n//2];pins.update({str(a):ch+('_P' if n%2==0 else '_N'),str(bb):ch+'_Q',str(y):ch+('_IN1' if n%2==0 else '_IN2')})
 expected[ref]=pins
for ref,pins in expected.items():
 actual={p.GetNumber():p.GetNetname() for p in fps[ref].Pads()};assert actual==pins,(ref,actual,pins)
report={'board_sha256':hashlib.sha256(board.read_bytes()).hexdigest(),'references_checked':sorted(expected),'pins_checked':sum(map(len,expected.values())),'pin_net_checks_passed':True,'datasheet_basis':{'U1':'Microchip DS21295D pp1,3,15; MCP3008 16-pin SOIC','U4_U5_U6':'TI SCLS081G pp3-4; SN74HC08 14-pin SOIC','U7':'Microchip DS11187F pp1-2,7,9; SOT23 rotated package views cross-checked'},'monitor':{'part':'MCP100T-300I/TT','trip_min_v':2.85,'trip_typ_v':2.925,'trip_max_v':3.0,'release_min_ms':150,'release_typ_ms':350,'release_max_ms':700,'output':'active-low push-pull','output_valid_down_to_vdd_v':1.0},'adc':{'supply_min_v':2.7,'supply_max_v':5.5,'example_spi_hz':500000,'datasheet_clock_max_hz_at_2v7':1350000,'spi_mode_candidates':[0,3],'sensor_source_impedance_verified':False},'physical_testing_performed':False,'jlcpcb_rotation_verified':False,'order_ready':False}
(root/'reports/ic-datasheet-review.json').write_text(json.dumps(report,indent=2)+'\n')
print('Manufacturer pin-role checks passed:',report['pins_checked'],'pins across',len(expected),'ICs')
