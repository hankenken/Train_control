#!/usr/bin/env python3
"""Render Japanese review PDF, not a manufacturing release."""
from pathlib import Path
import csv,json,zipfile
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from pypdf import PdfReader,PdfWriter
root=Path(__file__).resolve().parent
pdfmetrics.registerFont(TTFont('JP', '/tmp/train-pdf-fonts/NotoSansJP-400.ttf'))
style=ParagraphStyle('JP',fontName='JP',fontSize=9,leading=14,wordWrap='CJK',spaceAfter=9)
small=ParagraphStyle('small',parent=style,fontSize=7,leading=10)
def para(t):return Paragraph(escape(t),style)
report=json.loads((root/'reports/draft-checks.json').read_text())
story=[para('旧アナログ方式・採用対象外 — センサバッファ Rev B 45×32mm'),para('配置草案／未配線・発注不可'),
para('旧100×100mmを保存した別リビジョン。面積1,440mm²、旧版より85.6%削減。MCP6004×2と受動部品の実装21点、回路の電気的接続は維持しました。'),
para('8組のセンサ入力は上下4組ずつ配置。手はんだ用の直付け穴は0.8mm、パッド1.6mm、ピッチ2.0mm。M2用2.2mm取付穴を4個設けています。'),
para('出力は共通GND、3.3V、ADC0〜7をJ10の10線に集約。旧版のJ1とJ11〜J17は廃止しています。コネクタは実装しません。'),
para('3.3V専用です。12V・5Vや独立した別電源は接続しません。Pololu側とは番号ではなく信号名を照合して配線してください。'),
para('ERC違反0件、配置DRC違反0件。回路図と基板の100端子が一致。銅配線は0本で、未接続74件が残っています。配線・GND面・信号評価・部品調達・実装方向の確認は次工程です。'),
para('45×32mmは配線前の実用的な配置目標です。最終配線により微調整が必要な場合があり、理論上の最小寸法を証明したものではありません。'),
para('J10の接続（1番は角パッド。上から1/2、3/4、5/6、7/8、9/10）')]
data=[['番号','信号／接続']]+[[str(i),t] for i,t in [(1,'3.3V（ADCと共通のセンサ用電源）'),(2,'共通GND')]+[(i+3,f'ADC{i} → TC IO J{i+2}-3') for i in range(8)]]
t=Table([[Paragraph(escape(x),small) for x in row] for row in data],colWidths=[20*mm,150*mm]);t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.3,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7eef0'))]));story.extend([t,PageBreak(),para('部品・直付け位置一覧（LCSC調達未確定）')])
rows=list(csv.DictReader((root/'source/BOM_DRAFT.csv').open()));data=[['記号','候補型番／値','実装']]+[[r['Reference'],r['MPN_or_value'],'SMT' if r['Populate']=='True' else '部品なし：直付け穴'] for r in rows]
t=Table([[Paragraph(escape(x),small) for x in row] for row in data],colWidths=[20*mm,110*mm,40*mm],repeatRows=1);t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.3,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7eef0')),('VALIGN',(0,0),(-1,-1),'TOP')]))
story.append(t);overview=root/'review/overview_BOM_DRAFT.pdf';SimpleDocTemplate(str(overview),pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,topMargin=16*mm,bottomMargin=16*mm).build(story)
output=root/'review/TC_SENSOR_BUFFER_REVB_MINI_design_DRAFT.pdf';w=PdfWriter()
for f in [overview,root/'review/schematic_UNROUTED.pdf',root/'review/placement_UNROUTED.pdf']:w.append(str(f))
with output.open('wb') as f:w.write(f)
archive=root/'TC_SENSOR_BUFFER_REVB_MINI_DRAFT_NOT_FOR_ORDER.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for f in sorted(root.rglob('*')):
  if f.is_file() and f!=archive and f.suffix not in ['.prl','.pyc'] and '__pycache__' not in f.parts:z.write(f,f.relative_to(root))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
print(output.name,len(PdfReader(output).pages),'pages; ZIP CRC verified')
