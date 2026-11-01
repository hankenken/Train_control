#!/usr/bin/env python3
"""Bundle camera-only prototype, excluding older hardware designs and local data."""
from pathlib import Path
import hashlib,json,zipfile
root=Path(__file__).resolve().parent
archive=root/'dist/Train_camera_Pi5_prototype.zip'
archive.parent.mkdir(exist_ok=True)
files=[p for p in root.rglob('*') if p.is_file() and not {'dist','logs','recordings','__pycache__'}.intersection(p.relative_to(root).parts) and p.suffix!='.pyc' and not p.name.endswith('.local.json')]
manifest={'purpose':'Pi 5 camera/vision prototype; no physical outputs','hardware_outputs_enabled':False,'pi5_capture_tested_on_hardware':False,'files':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(files):z.write(p,'camera_control/'+str(p.relative_to(root)))
 z.write(root/'START_HERE_JA.md','START_HERE_JA.md')
 z.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 for n,h in manifest['files'].items():assert hashlib.sha256(z.read('camera_control/'+n)).hexdigest()==h
print(archive.name,len(files),'files',archive.stat().st_size,'bytes; CRC/hashes verified')
