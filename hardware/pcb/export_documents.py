#!/usr/bin/env python3
"""Create Japanese Rev B BOM, assembly guide and combined PDF.

Requires reportlab, pypdf and fonttools; KiCad exports must already exist.
The official Noto Sans JP font is downloaded with TLS verification if absent.
No PCB, schematic, fabrication data or component values are modified.
"""
from pathlib import Path
from urllib.request import urlopen
from xml.sax.saxutils import escape
import csv, hashlib, json, shutil, tempfile

from fontTools.ttLib import TTFont as FontToolsFont
from fontTools.varLib.instancer import instantiateVariableFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from pypdf import PdfReader, PdfWriter

ROOT=Path(__file__).resolve().parent
REVIEW=ROOT/'review'; SRC=ROOT/'source'; NAME='TC_IO_REVB'
CACHE=Path(tempfile.gettempdir())/'train-pdf-fonts'; CACHE.mkdir(exist_ok=True)
font=CACHE/'NotoSansJP.ttf'
FONT_URL='https://raw.githubusercontent.com/google/fonts/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf'
if not font.exists():
    with urlopen(FONT_URL,timeout=60) as response: font.write_bytes(response.read())
for weight,name in [(400,'JP'),(700,'JPB')]:
    target=CACHE/f'NotoSansJP-{weight}.ttf'
    if not target.exists():
        static=instantiateVariableFont(FontToolsFont(font),{'wght':weight},inplace=False)
        static.save(target)
    pdfmetrics.registerFont(TTFont(name,str(target)))
pdfmetrics.registerFontFamily('JP',normal='JP',bold='JPB',italic='JP',boldItalic='JPB')

styles={
 'title':ParagraphStyle('title',fontName='JPB',fontSize=18,leading=25,spaceAfter=10),
 'heading':ParagraphStyle('heading',fontName='JPB',fontSize=11,leading=16,spaceBefore=8,spaceAfter=6),
 'body':ParagraphStyle('body',fontName='JP',fontSize=9,leading=14,spaceAfter=6,wordWrap='CJK'),
 'cell':ParagraphStyle('cell',fontName='JP',fontSize=8,leading=11,wordWrap='CJK'),
 'headcell':ParagraphStyle('headcell',fontName='JPB',fontSize=8,leading=11,textColor=colors.white,wordWrap='CJK'),
}
def para(text,style='body'):return Paragraph(text,styles[style])
def table(headers,rows,widths):
    values=[[para(escape(str(x)),'headcell') for x in headers]]
    values += [[para(escape(str(x)),'cell') for x in row] for row in rows]
    t=Table(values,colWidths=[v*mm for v in widths],repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#254755')),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f0f4f5')]),
        ('GRID',(0,0),(-1,-1),.35,colors.HexColor('#bac8ce')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
    ]));return t
def footer(canvas,doc):
    canvas.saveState();canvas.setFont('JP',8);canvas.setFillColor(colors.HexColor('#526873'))
    canvas.drawString(12*mm,10*mm,'TC IO Rev B / 100 × 100 mm / 実機未検証の試作版')
    canvas.drawRightString(198*mm,10*mm,str(doc.page));canvas.restoreState()
def build(path,story):
    doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=12*mm,leftMargin=12*mm,
        topMargin=14*mm,bottomMargin=18*mm,title=path.stem,author='Train_control')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)

rows=list(csv.DictReader((SRC/'BOM_hand_assembly.csv').open(newline='')))
byref={row['Reference']:row for row in rows}
assert len(byref)==49
groups=[
 ('U1','MCP3008-I/P','DIP16','3.3V動作の8ch ADC。ソケット使用。'),
 ('U2 U3','SN74HC221N','DIP16','非再トリガ型。LS/HCT品への置換不可。'),
 ('U4 U5 U6','SN74HC08N','DIP14','4回路AND。ソケット使用。'),
 ('U7','MCP100-300DI/TO','TO-92','電源監視。実部品のピン順を照合。'),
 ('RN1 RN2 RN3','4609X-101-103LF','SIP9','8×10kΩ共通型。1番共通、独立型不可。'),
 ('R1 R2 R3 R4','150 kΩ ±1%','軸型・P7.62mm','パルス時間設定。実測で確認。'),
 ('R5','10 kΩ','軸型・P7.62mm','ADC CSのプルアップ。'),
 ('C1 C2 C3 C4','470 nF ±5% フィルム','P7.50mm','本体約10.3×5mm以内。タイマー用。'),
 ('C5 C6 C7 C8 C9 C10 C11 C12','100 nF（0.1 µF）','円板型・P2.50mm','本体径5mm以内。電源バイパス。'),
 ('C13','10 µF / 16V以上','電解・P2.00mm','本体径5mm。＋極の向きに注意。'),
 ('J1','40ピンIDC基板ヘッダ','2×20・P2.54mm','垂直・ボックス型。ケーブルは別途。'),
 ('J2 J3 J4 J5 J6 J7 J8 J9','JST B3B-XH-A','3極・P2.50mm','センサ入力用。1=GND / 2=3.3V / 3=OUT。'),
 ('J10 J11 J12 J13','JST B3B-XH-A','3極・P2.50mm','DRV論理出力。1=GND / 2=IN1 / 3=IN2。'),
 ('J14','ピンヘッダ 1×4','P2.54mm','将来用I²C。現在は予約端子。'),
 ('JP1','ピンヘッダ 1×2','P2.54mm','センサ電源。初期状態は開放。'),
 ('TP1 TP2 TP3 TP4 TP5 TP6','ピンヘッダ 1×2','P2.54mm','測定端子。2番はGND。'),
]
covered=[];bom=[]
for refs,value,shape,note in groups:
    refs=refs.split();covered+=refs
    qty=sum(int(byref[ref]['Quantity']) for ref in refs)
    label='・'.join(refs) if len(refs)<=3 else refs[0]+'〜'+refs[-1]
    bom.append([label,value,qty,shape,note])
assert len(covered)==len(set(covered)) and set(covered)==set(byref)
assert sum(row[2] for row in bom)==49

bom_path=REVIEW/(NAME+'_BOM.pdf')
story=[para('部品表','title'),para('TC IO Rev B　100 × 100 mm / 手はんだ組立用'),
 para('基板実装部品：49点（ICソケット・ケーブル等は次ページ）。原本は source/BOM_hand_assembly.csv。'),
 table(['部品番号','品名・値 / 型番','数量','実装形状','注意事項'],bom,[27,47,11,34,67]),
 PageBreak(),para('付属品・外部機器','title'),
 para('以下は基板実装部品49点とは別です。購入前に端子形状・ピン配置・定格を照合してください。'),
 table(['品名','数量','用途・条件'],[
  ['DIP16ソケット','3','U1〜U3用。基板のフットプリントはソケット外形を確保。'],
  ['DIP14ソケット','3','U4〜U6用。'],
  ['40ピンIDCケーブル','1','Pi 4とJ1を接続。両端の1番位置と導通を確認。'],
  ['JST XH 3極ハウジング','12','J2〜J13に適合するハウジング。センサ・DRVで結線順が異なる。'],
  ['上記ハウジング用コンタクト','36','電線サイズに合う圧着端子。予備は別途。'],
  ['2.54mmショートピン','1','JP1用。全センサの電流予算を確認するまでは取り付けない。'],
  ['M3ねじ・絶縁スペーサ','4組','3.2mm取付穴。固定方法に応じた長さとナットを選ぶ。'],
  ['DRV8871完成モジュール','4（案）','基板外。3.3V入力・電流制限・放熱条件の資料照合が必要。'],
  ['一体型アナログ反射センサ','8（予定）','基板外。3.3V対応、屋根まで約10mmの実測が必要。型番未確定。'],
  ['ポイント用DC12V電源','1（案）','別系統。2A以上を初期候補とし、同時駆動を禁止する設計。'],
  ['ヒューズ・出力停止スイッチ','別途設計','12V負荷側。適切なDC定格・配線保護を確認。'],
 ],[55,21,110]),
 para('設計上の確認事項','heading'),
 para('タイマーのRC値は約50msの試算です。ポイントを接続する前にパルス幅を実測し、100ms以下を確認します。'),
 para('ICのメーカー資料による独立確認・電流制限の確定・実機試験は未完了です。信号灯とLED表示の駆動部品は今回の基板に含みません。'),
]
build(bom_path,story)

intro=REVIEW/'assembly-instructions.pdf'
story=[para('組立図・接続案内','title'),para('TC IO Rev B　100 × 100 mm / 部品面から見た図を次ページに収録'),
 para('基板はPiに重ねるHATではありません。40ピンケーブルで接続する独立基板です。部品面から見た配置図は反転せずに使用します。'),
 para('組立順','heading'),
 para('1. 基板の向きと部品番号を確認し、抵抗・抵抗ネットワークから取り付けます。'),
 para('2. ICソケット、コンデンサ、ヘッダ、コネクタを取り付けます。C13の極性、ソケットの切欠き、RNの1番共通端子に注意します。'),
 para('3. ICを挿す前に短絡・はんだブリッジを確認します。ICは電源を切って挿入し、切欠きと1番を図面に合わせます。'),
 para('4. JP1は開放。センサ・DRV・ポイントを未接続にして、3.3Vと起動時の出力禁止を測定します。'),
 para('5. RCパルス幅を確認し、センサ1個、DRVのダミー負荷、ポイント1台の順に試験します。'),
 para('接続端子','heading'),
 table(['端子','接続先 / ピン順'],[
  ['J1','Pi 4の40ピン。両端の1番を確認。5Vピンは本基板では未接続。'],
  ['J2/J3、J4/J5','上側外側A/B、上側内側A/B。'],
  ['J6/J7、J8/J9','下側外側A/B、下側内側A/B。'],
  ['J2〜J9共通','1=GND、2=センサ3.3V、3=アナログOUT。'],
  ['J10/J11、J12/J13','上側外側/内側、下側外側/内側のDRVロジック出力。'],
  ['J10〜J13共通','1=GND、2=IN1、3=IN2。12Vやポイントの青白線は接続しない。'],
  ['J14','1=GND、2=3.3V、3=SDA、4=SCL。将来用。'],
  ['TP1 / TP2','1=CLR_N / POWER_GOOD、2=GND。'],
  ['TP3〜TP6','1=各チャンネルQパルス、2=GND。'],
 ],[40,146]),
 para('取付・初回確認','heading'),
 para('取付穴は直径3.2mm、中心間隔92×92mm。穴中心は外形から各4mmです。配置図を原寸印刷する場合は倍率100%とし、外形が100mmになることを実測してください。'),
 para('Webアプリの実機GPIO出力は未実装です。DRV8871と12V負荷回路は基板外です。資料だけで転換完了や正常動作が保証されるものではありません。'),
]
build(intro,story)
assembly_path=REVIEW/(NAME+'_assembly.pdf')
writer=PdfWriter();writer.append(str(intro));writer.append(str(REVIEW/'assembly-top.pdf'))
writer.add_metadata({'/Title':'TC IO Rev B - 組立図・接続案内'})
with assembly_path.open('wb') as f:writer.write(f)
intro.unlink()
schematic_path=REVIEW/(NAME+'_schematic.pdf');shutil.copy2(REVIEW/'schematic.pdf',schematic_path)

cover=REVIEW/'document-cover.pdf'
board_sha=hashlib.sha256((SRC/(NAME+'.kicad_pcb')).read_bytes()).hexdigest()
doc_paths=[schematic_path,bom_path,assembly_path]
counts=[len(PdfReader(p).pages) for p in doc_paths]
build(cover,[para('路面電車 運行管理','title'),para('TC IO Rev B　回路図・部品表・組立図','heading'),
 para('100 × 100 mm / 2層 / Raspberry Pi 4 Model B用 制御基板'),Spacer(1,8*mm),
 table(['資料','ページ数','内容'],[
  ['回路図',counts[0],'A1のベクター図面。画面で拡大して閲覧。'],
  ['部品表',counts[1],'基板実装49点、ソケット・ケーブル等の付属品。'],
  ['組立図',counts[2],'組立順・接続表と、部品面から見た配置図。'],
 ],[35,20,131]),Spacer(1,10*mm),
 para('実機未検証の試作版です。8センサ入力と4系統のパルス制御を搭載し、DRV8871の完成モジュール、12V負荷電源、実物センサは基板外に接続します。'),
 para('旧Rev A（170×120mm）の資料とは区別してください。本資料は100×100mmのRev Bから出力しています。'),
 para('基板ソースSHA-256','heading'),para(board_sha),
])
combined=REVIEW/(NAME+'_documents.pdf')
writer=PdfWriter();writer.append(str(cover))
for path,title in zip(doc_paths,['回路図','部品表','組立図・接続案内']):writer.append(str(path),outline_item=title)
writer.add_metadata({'/Title':'TC IO Rev B - 回路図・部品表・組立図','/Author':'Train_control'})
with combined.open('wb') as f:writer.write(f)
cover.unlink()
report={'board':NAME,'board_source_sha256':board_sha,'bom_source_sha256':hashlib.sha256((SRC/'BOM_hand_assembly.csv').read_bytes()).hexdigest(),
        'grouped_components':len(groups),'board_component_quantity':49,
        'font_source':FONT_URL,'pdfs':{}}
for path in [*doc_paths,combined]:
    reader=PdfReader(path);assert not reader.is_encrypted and len(reader.pages)>0
    report['pdfs'][path.name]={'pages':len(reader.pages),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    print(path.name,len(reader.pages),'pages')
assert len(PdfReader(combined).pages)==1+sum(counts)
(ROOT/'reports/pdf-documents.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
