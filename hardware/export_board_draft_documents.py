#!/usr/bin/env python3
"""Japanese review PDFs for unrouted boards. No fabrication exports."""
from pathlib import Path
import csv,json,hashlib,urllib.request,zipfile
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
style=ParagraphStyle('jp',fontName='JP',fontSize=9,leading=14,wordWrap='CJK',spaceAfter=8)
small=ParagraphStyle('small',parent=style,fontSize=7,leading=10)
def para(s):return Paragraph(escape(s),style)
for folder,name,title,summary in [('driver-board','TC_DRIVE_REVA','4系統 ポイント駆動基板',[
'100×100mm／2層／12V専用／実装35点／コネクタなし。未配線の回路・配置案です。',
'DRV8871DDARを4個使用。既存制御基板J10〜J13のGND/IN1/IN2へ対応。ワンショットとVRは既存基板が担当します。',
'電流制限は53.6kΩ±1%。公称1.194A、資料と抵抗誤差の計算範囲約1.090〜1.300A。電流を必ずこの値まで流す回路ではありません。',
'12V入力に外部ヒューズ・停止スイッチ。基板上は逆接用直列ダイオード、TVS、共通470µF＋各系統100µFと100nFの案。保護協調と回生は未検証。',
'各出力は青・白の2線へ。方向対応は実機で校正。1系統ずつ駆動し、Piへコイル電流を戻さない配線にします。',
'露出パッドとサーマルビアを含む配線・銅箔面・熱設計は次工程。部品コードと電解コンデンサ・保護部品の具体型番も未確定。']),
('sensor-buffer','TC_SENSOR_BUFFER_REVA','8入力 センサバッファ基板',[
'100×100mm／2層／3.3V専用／実装21点／コネクタなし。未配線の回路・配置案です。',
'MCP6004T-I/SLを2個使い、8個の電圧フォロワを構成。Pololu QTRX-HD-01AのアナログOUTを既存MCP3008へ接続する案です。',
'QTRX-HD-01Aは幅約5mm・長さ20mm・最適距離10mm・最大5mA。完成モジュールを架線柱へ、バッファ基板は制御基板の近くへ置きます。',
'モジュール内部の47kΩプルアップによる出力源インピーダンスを考慮してバッファを追加。出力100Ω＋1nFは初期案で、ケーブル容量とADC誤差を測定します。',
'センサ8個最大40mA＋アンプ8個典型0.8mAに、既存制御基板の電流を加えて電源を確認。独立外部電源・5V・12Vは使用しません。',
'車両の色・屋根・照明・パンタグラフとの干渉、ADCの取得時間は未検証。メーカーの最適距離は全車両での検出保証ではありません。'])]:
 p=root/folder;report=json.loads((p/'reports/draft-checks.json').read_text())
 story=[para(title+' Rev A — 設計草案'),para('未配線・発注不可／実機未検証')]+[para(s) for s in summary]
 story +=[para(f"ERC違反：{report['erc_violations']}／回路図と基板の端子接続一致：{report['net_assignment_count']}端子。"),para(f"配置段階のDRC指摘：{report['pcb_drc_violations']}件／未接続：{report['unconnected_items']}件。ERC合格は実機動作や製造準備完了を意味しません。"),PageBreak(),para('部品表草案 — LCSC調達は未確定')]
 rows=list(csv.DictReader((p/'source/BOM_DRAFT.csv').open()));data=[[Paragraph(t,small) for t in ['記号','候補型番・値','配置・実装']]]
 for r in rows:
  if r['Reference'].startswith('#'):continue
  data.append([Paragraph(escape(t),small) for t in [r['Reference'],r['MPN_or_value'],r['Footprint'].split(':')[-1] if r['Populate']=='True' else '部品なし：電線直付け']])
 table=Table(data,colWidths=[20*mm,79*mm,75*mm],repeatRows=1);table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.3,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5edf0')),('VALIGN',(0,0),(-1,-1),'TOP')]))
 story.append(table);overview=p/'review/overview_BOM_DRAFT.pdf';SimpleDocTemplate(str(overview),pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,topMargin=18*mm,bottomMargin=18*mm).build(story)
 output=p/'review'/(name+'_design_DRAFT.pdf');w=PdfWriter()
 for f in [overview,p/'review/schematic_UNROUTED.pdf',p/'review/placement_UNROUTED.pdf']:w.append(str(f))
 with output.open('wb') as f:w.write(f)
 print(output.name,len(PdfReader(output).pages),'pages')
 # A review package with no Gerber manufacturing data.
 archive=p/(name+'_DESIGN_DRAFT_NOT_FOR_ORDER.zip')
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
  for f in sorted(p.rglob('*')):
   if f.is_file() and f!=archive and f.suffix not in ['.prl','.pyc'] and '__pycache__' not in f.parts:z.write(f,f.relative_to(p))
 with zipfile.ZipFile(archive) as z:assert z.testzip() is None
