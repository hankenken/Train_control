#!/usr/bin/env python3
"""Bundle the PC camera test; excludes live driver/COM tools and local data."""
from pathlib import Path
import hashlib,json,zipfile
root=Path(__file__).resolve().parent
archive=root/'dist/Train_camera_PC_test.zip'
archive.parent.mkdir(exist_ok=True)
files=[p for p in root.rglob('*') if p.is_file() and not {'dist','logs','recordings','__pycache__','output_bridge'}.intersection(p.relative_to(root).parts) and p.suffix!='.pyc' and not p.name.endswith('.local.json') and p.name!='test_output_bridge.py']
manifest={'purpose':'Windows10 PC/LattePanda USB camera recognition and mock-output test','hardware_outputs_enabled':False,'live_driver_tools_included':False,'windows10_capture_tested_on_hardware':False,'calibration':'4 screen clicks; fresh empty background required','files':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(files):z.write(p,'camera_control/'+str(p.relative_to(root)))
 z.write(root/'PC_CAMERA_TEST_JA.md','START_HERE_JA.md')
 z.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 for n,h in manifest['files'].items():assert hashlib.sha256(z.read('camera_control/'+n)).hexdigest()==h
print(archive.name,len(files),'files',archive.stat().st_size,'bytes; CRC/hashes verified')
