#!/usr/bin/env python3
"""Japanese mini-driver review PDF; no manufacturing data."""
from pathlib import Path
import csv,json,urllib.request,zipfile
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from pypdf import PdfReader,PdfWriter
from fontTools.ttLib import TTFont as FTFont
from fontTools.varLib.instancer import instantiateVariableFont
root=Path(__file__).resolve().parent;cache=Path('/tmp/train-pdf-fonts');cache.mkdir(exist_ok=True)
font=cache/'NotoSansJP.ttf';static=cache/'NotoSansJP-400.ttf'
if not font.exists():
 with urllib.request.urlopen('https://raw.githubusercontent.com/google/fonts/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf',timeout=30) as r:font.write_bytes(r.read())
if not static.exists():instantiateVariableFont(FTFont(font),{'wght':400},inplace=False).save(static)
pdfmetrics.registerFont(TTFont('JP',str(static)))
style=ParagraphStyle('jp',fontName='JP',fontSize=9,leading=14,wordWrap='CJK',spaceAfter=8);small=ParagraphStyle('small',parent=style,fontSize=7,leading=10)
def para(s):return Paragraph(escape(s),style)
report=json.loads((root/'reports/draft-checks.json').read_text())
summary=['ポイント駆動基板 TC DRIVE Rev B — 小型配置案','60×45mm（暫定）、2層。100mm角から面積73%減。4系統・35点の表面実装と電線直付け9組を維持。','未配線・製造不可。厳密な最小寸法や実機動作の保証ではありません。','DRV8871×4、53.6kΩ、電源逆接用ダイオード・TVS候補・共通470µFと各100µF/100nFを配置。電気的ネット・値はRev Aと一致。','制御入力はGND/IN1/IN2。ワンショットと各VRは既存TC IO側が担当。12V専用・1系統ずつの通電が前提。','取付穴をM3からM2用2.2mmへ変更（4個）。外形から3mm、中心間54×39mm。Rev Aと取付互換はありません。','DDAは専用フットプリント。熱逃がし穴0.3mm、ランド0.6mm、各IC8穴。露出パッドのはんだ付けと裏面GND面・熱設計は次工程。',f"ERC：0件。配置DRC：0件。回路図・基板の120端子割当が一致。銅箔間隔規則0.20mm。未接続{report['unconnected_items']}件／配線0本。",'電流・回生・温度と、部品調達・実装条件を確認してから配線し、寸法を再検証します。配置検査だけで発注できる状態ではありません。']
story=[para(s) for s in summary]+[PageBreak(),para('部品表草案 — 型番・調達未確定の候補を含む')]
rows=list(csv.DictReader((root/'source/BOM_DRAFT.csv').open()));data=[[Paragraph(t,small) for t in ['記号','候補型番・値','配置・実装']]]
for r in rows:
 if r['Reference'].startswith('#'):continue
 data.append([Paragraph(escape(t),small) for t in [r['Reference'],r['MPN_or_value'],r['Footprint'].split(':')[-1] if r['Populate']=='True' else '部品なし：電線直付け']])
table=Table(data,colWidths=[20*mm,79*mm,75*mm],repeatRows=1);table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.3,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5edf0')),('VALIGN',(0,0),(-1,-1),'TOP')]));story.append(table)
overview=root/'review/overview_BOM_DRAFT.pdf';SimpleDocTemplate(str(overview),pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,topMargin=18*mm,bottomMargin=18*mm).build(story)
output=root/'review/TC_DRIVE_REVB_design_DRAFT.pdf';w=PdfWriter()
for f in [overview,root/'review/schematic_UNROUTED.pdf',root/'review/placement_UNROUTED.pdf']:w.append(str(f))
with output.open('wb') as f:w.write(f)
archive=root/'TC_DRIVE_REVB_DESIGN_DRAFT_NOT_FOR_ORDER.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for f in sorted(root.rglob('*')):
  if f.is_file() and f!=archive and f.suffix not in ['.prl','.pyc'] and '__pycache__' not in f.parts:z.write(f,f.relative_to(root))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
print(output.name,len(PdfReader(output).pages),'pages; archive CRC passed')
