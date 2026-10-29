#!/usr/bin/env python3
from pathlib import Path
import csv,json,zipfile
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from pypdf import PdfWriter,PdfReader
root=Path(__file__).resolve().parent
font=Path('/tmp/train-pdf-fonts/NotoSansJP-400.ttf')
if not font.exists():
 import urllib.request
 from fontTools.ttLib import TTFont as FontToolsFont
 from fontTools.varLib.instancer import instantiateVariableFont
 font.parent.mkdir(exist_ok=True)
 variable=font.parent/'NotoSansJP.ttf'
 if not variable.exists():
  with urllib.request.urlopen('https://raw.githubusercontent.com/google/fonts/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf',timeout=30) as response:variable.write_bytes(response.read())
 instantiateVariableFont(FontToolsFont(variable),{'wght':400},inplace=False).save(font)
pdfmetrics.registerFont(TTFont('JP',str(font)))
style=ParagraphStyle('jp',fontName='JP',fontSize=9,leading=14,wordWrap='CJK',spaceAfter=8)
small=ParagraphStyle('small',parent=style,fontSize=7,leading=10)
def p(s):return Paragraph(escape(s),style)
def table(rows,widths):
 t=Table([[Paragraph(escape(str(v)),small) for v in row] for row in rows],colWidths=[x*mm for x in widths],repeatRows=1)
 t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.3,colors.grey),('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e6eef0'))]));return t
r=json.loads((root/'reports/draft-checks.json').read_text())
story=[p('TC IO Rev D MINI — ToF対応小型制御基板'),p('50×40mm 暫定配置案／未配線・発注不可'),
p('100mm角から面積80%減。ポイント4系統のパルス・方向ゲート・個別VR・電源監視を維持し、ToFで不要になるADC、ADC用抵抗・バイパスを削除。実装46点、コネクタなし。'),
p('既存の100mm角Rev Cを変更したデータではありません。JLCPCBの旧配置補正は小型版に流用せず、新しいデータで再確認します。'),
p('VL53L4CD×8は別のI2C切替・専用センサ電源基板へ接続予定。その基板は未確定。制御基板J4はPi側のロジック電源・SDA・SCL・GNDで、8台の給電用ではありません。'),
p('J1の番号はPiの物理番号とは異なります。次ページの配線表を使用してください。取付はM2穴×4へ変更、旧M3固定とは互換性がありません。'),
p(f"ERC 0件、配置DRC 0件、回路図と基板{r['net_assignment_count']}端子一致。保持46部品の値・端子ネットはRev Cと一致。未接続{r['unconnected_items']}件、配線0本。配線後の寸法維持・動作・放熱を保証したデータではありません。"),
p('時間はユーザー指定の概略値としてC2167387とVRで実測調整。厳密な100ms上限精度は要求しません。ToFの距離status判定・読出しタイミング・実機ソフトは未実装です。'),PageBreak(),p('Pi配線表 — MINI J1 → Raspberry Pi物理端子')]
rows=list(csv.DictReader((root/'source/pi-wiring.csv').open()));story.append(table([['MINI J1','Pi物理端子','ネット']]+[[r['mini_pad'],r['pi_physical_pin'],r['net']] for r in rows]+[['18','接続しない','NC']],[25,40,105]))
story+=[p('J4：1 GND、2 Pi側3.3Vロジック、3 SDA、4 SCL。外部センサ用3.3VをPi電源へ並列接続しない。'),p('J3：1 GND、2/3 UP_OUT、4/5 UP_IN、6/7 LOW_OUT、8/9 LOW_INのIN1/IN2、10 NC。駆動基板側の同名J番号と混同しない。'),PageBreak(),p('部品表 — 草案')]
rows=list(csv.DictReader((root/'source/BOM_DRAFT.csv').open()));story.append(table([['記号','型番・値','実装／端子群']]+[[r['Reference'],r['MPN_or_value'],r['Footprint'].split(':')[-1] if r['Populate']=='True' else '部品なし・直付け/測定パッド'] for r in rows],[20,80,70]))
f=root/'review/overview_BOM_wiring_DRAFT.pdf';SimpleDocTemplate(str(f),pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,topMargin=18*mm,bottomMargin=18*mm).build(story)
fout=root/'review/TC_IO_REVD_MINI_design_DRAFT.pdf';w=PdfWriter()
for x in [f,root/'review/schematic_UNROUTED.pdf',root/'review/placement_UNROUTED.pdf']:w.append(str(x))
with fout.open('wb') as f:w.write(f)
a=root/'TC_IO_REVD_MINI_DESIGN_DRAFT_NOT_FOR_ORDER.zip'
with zipfile.ZipFile(a,'w',zipfile.ZIP_DEFLATED) as z:
 for f in sorted(root.rglob('*')):
  if f.is_file() and f!=a and f.suffix not in ['.prl','.pyc'] and '__pycache__' not in f.parts:z.write(f,f.relative_to(root))
with zipfile.ZipFile(a) as z:assert z.testzip() is None
print(fout.name,len(PdfReader(fout).pages),'pages; draft archive CRC verified')
