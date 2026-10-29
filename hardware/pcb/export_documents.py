#!/usr/bin/env python3
"""Create Japanese Rev C BOM, assembly guide and combined PDF.

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
REVIEW=ROOT/'review'; SRC=ROOT/'source'; NAME='TC_IO_REVC'
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
    canvas.drawString(12*mm,10*mm,'TC IO Rev C / 100 × 100 mm / 実機未検証・PCBA準備中')
    canvas.drawRightString(198*mm,10*mm,str(doc.page));canvas.restoreState()
def build(path,story):
    doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=12*mm,leftMargin=12*mm,
        topMargin=14*mm,bottomMargin=18*mm,title=path.stem,author='Train_control')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)

all_rows=list(csv.DictReader((SRC/'BOM_hand_assembly.csv').open(newline='')))
rows=[r for r in all_rows if r['Populate']=='yes']
byref={row['Reference']:row for row in rows}
assert len(byref)==50
groups=[
 ('U1','MCP3008T-I/SL','SOIC16','8ch ADC。LCSC掲載・端子図照合待ち。'),
 ('U2 U3','CD74HC221M96','SOIC16','非再トリガ型。C133954掲載を提供画面で確認。3.3Vの時間特性は評価待ち。'),
 ('U4 U5 U6','SN74HC08DR','SOIC14','4回路AND。表面実装。'),
 ('U7','MCP100T-300I/TT','SOT-23','電源監視。実部品のピン順を照合。'),
 ('R1 R2 R3 R4','150 kΩ ±1%','0805','各VRと直列の固定抵抗。'),
 ('R5 R6 R7 R8 R9 R10 R11 R12 R13 R14 R15 R16 R17 R18 R19 R20 R21 R22 R23 R24 R25 R26','10 kΩ ±1%','0805','R5=プルアップ、R6〜R26=プルダウン。'),
 ('VR1 VR2 VR3 VR4','3224W-1-104E / 100 kΩ','SMD多回転','工場実装対象。2番と3番を接続。'),
 ('C1 C2 C3 C4','470 nF ±5% / 50V X7R','1206','タイミング用。DCバイアス・温度特性を要確認。'),
 ('C5 C6 C7 C8 C9 C10 C11 C12','100 nF / 50V X7R','0805','電源バイパス。'),
 ('C13','10 µF / 25V X7R','1206','無極性MLCC。実効容量を確認。'),
]
covered=[];bom=[]
for refs,value,shape,note in groups:
    refs=refs.split();covered+=refs
    qty=sum(int(byref[ref]['Quantity']) for ref in refs)
    label='・'.join(refs) if len(refs)<=3 else refs[0]+'〜'+refs[-1]
    bom.append([label,value,qty,shape,note])
assert len(covered)==len(set(covered)) and set(covered)==set(byref)
assert sum(row[2] for row in bom)==50

bom_path=REVIEW/(NAME+'_BOM.pdf')
story=[para('部品表（実装依頼・草案）','title'),para('TC IO Rev C　100 × 100 mm / JLCPCB実装依頼の準備資料'),
 para('基板実装部品：50点。全点が表面実装で、JLCPCBでの実装可否・在庫・LCSC部品番号は未確認です。発注用の確定BOMではありません。'),
 table(['部品番号','品名・値 / 型番','数量','実装形状','注意事項'],bom,[27,47,11,34,67]),
 PageBreak(),para('付属品・外部機器','title'),
 para('以下は基板実装部品50点とは別です。購入前に端子形状・ピン配置・定格を照合してください。'),
 table(['品名','数量','用途・条件'],[
  ['接続用電線・引張り止め','必要数','基板にコネクタは実装せず、配線穴へ電線を直付け。'],
  ['M3ねじ・絶縁スペーサ','4組','3.2mm取付穴。ケース固定用。'],
  ['Pi 4と専用USB-C電源','各1','本基板とは別。3.3V信号の配線位置を確認。'],
  ['DRV8871完成モジュール','4（案）','基板外。3.3V入力・電流制限・放熱条件の資料照合が必要。'],
  ['一体型アナログ反射センサ','8（予定）','基板外。3.3V対応、屋根まで約10mmの実測が必要。型番未確定。'],
  ['ポイント用DC12V電源','1（案）','別系統。2A以上を初期候補とし、同時駆動を禁止する設計。'],
  ['ヒューズ・出力停止スイッチ','別途設計','12V負荷側。適切なDC定格・配線保護を確認。'],
 ],[55,21,110]),
 para('設計上の確認事項','heading'),
 para('R=150kΩ＋VR 0〜100kΩ、C=470nF。典型式による計算は約49〜82msです。ポイント接続前に実測し、使用条件で100ms以下になることを確認します。計算だけで上限は保証されません。'),
 para('コネクタ・ヘッダ・ICソケットは実装しません。配線/測定パッド21グループは購入部品ではありません。メーカー資料の照合・実機試験も未完了です。信号灯とLED表示の駆動部品は今回の基板に含みません。'),
]
build(bom_path,story)

intro=REVIEW/'assembly-instructions.pdf'
story=[para('組立図・接続案内','title'),para('TC IO Rev C　100 × 100 mm / 部品面から見た配置図を後続ページに収録'),
 para('基板はPiに重ねるHATではありません。Piの40端子番号に対応した電線で接続する独立基板です。基板にコネクタは取り付けません。部品面から見た配置図は反転せずに使用します。'),
 para('IC・抵抗・コンデンサ・VRの表面実装50点を依頼する方針です。コネクタは使わず、電線直結用の穴を残します。調達部品・実装対応・CPLの中心と回転は未確認です。現時点では実装注文には使えません。'),
 para('受取後の検品・初回接続','heading'),
 para('1. 実装品を受け取ったら、部品面の番号・型番・向きを確定済みBOMと照合します。'),
 para('2. ICのピン1、VRの向き、チップ抵抗/コンデンサの実装を確認します。コンデンサは無極性MLCCです。'),
 para('3. 無通電で短絡・はんだブリッジを確認します。コネクタ部品は実装せず、角パッドが1番の配線穴へ必要な電線を接続します。'),
 para('4. JP1は開放。センサ・DRV・ポイントを未接続にして、3.3Vと起動時の出力禁止を測定します。'),
 para('5. RCパルス幅を確認し、センサ1個、DRVのダミー負荷、ポイント1台の順に試験します。'),
 para('電線直結用パッド','heading'),
 table(['端子','接続先 / ピン順'],[
  ['J1','Pi 4の端子番号と対応する配線穴。必要な信号だけ接続。5V端子は本基板では未接続。'],
  ['J2/J3、J4/J5','上側外側A/B、上側内側A/B。'],
  ['J6/J7、J8/J9','下側外側A/B、下側内側A/B。'],
  ['J2〜J9共通','1=GND、2=センサ3.3V、3=アナログOUT。'],
  ['J10/J11、J12/J13','上側外側/内側、下側外側/内側のDRVロジック出力。'],
  ['J10〜J13共通','1=GND、2=IN1、3=IN2。12Vやポイントの青白線は接続しない。'],
  ['J14','1=GND、2=3.3V、3=SDA、4=SCL。将来用。'],
  ['JP1','センサ給電用の開放パッド。電流予算の確認までは接続しない。ヘッダ部品なし。'],
  ['TP1 / TP2','1=CLR_N / POWER_GOOD、2=GND。'],
  ['TP3〜TP6','1=各チャンネルQパルス、2=GND。'],
 ],[40,146]),
 para('取付・初回確認','heading'),
 para('取付穴は直径3.2mm、中心間隔92×92mm。穴中心は外形から各4mmです。配置図を原寸印刷する場合は倍率100%とし、外形が100mmになることを実測してください。'),
 para('Webアプリの実機GPIO出力は未実装です。DRV8871と12V負荷回路は基板外です。資料だけで転換完了や正常動作が保証されるものではありません。'),
 PageBreak(),para('パルス幅の個別調整','title'),
 para('VR1〜VR4は、ポイント駆動パルスの長さを調整します。センサA→Bの時間判定やLED切替間隔を調整するVRではありません。'),
 table(['VR','対象チャンネル','測定端子'],[
  ['VR1','上側・外側（UP_OUT）','TP3の1番と2番GND'],
  ['VR2','上側・内側（UP_IN）','TP4の1番と2番GND'],
  ['VR3','下側・外側（LOW_OUT）','TP5の1番と2番GND'],
  ['VR4','下側・内側（LOW_IN）','TP6の1番と2番GND'],
 ],[20,85,81]),
 para('調整方法','heading'),
 para('1. ポイントと12V負荷電源を外し、ARMを解除して通電要求を禁止します。測定には3.3Vの試験信号とオシロスコープ等が必要です。GPIOドライバはまだ未実装です。'),
 para('2. VRを最小抵抗側に設定します。回転方向は採用部品の端子図・実物で確認してください。VRの調整はパルスが出ていない状態で行います。'),
 para('3. 測定準備後にARMを許可し、対象チャンネルへ単発トリガを与え、TPのQパルス幅を測ります。まず約50msへ合わせます。'),
 para('4. 再びARMを解除してVRを少しずつ調整し、同じ測定を繰り返します。ほかの3系統も個別に確認します。'),
 para('5. 最小・中間・最大位置、想定する電源・温度条件でパルス幅を確認します。100msを超える場合は負荷を接続せず、R/Cを再設計します。'),
 para('6. その後、ドライバのダミー負荷試験と実物ポイントの転換試験を行い、必要最小限のパルス幅を選びます。'),
 para('可変範囲と保護の限界','heading'),
 para('典型式 t≈0.7RC では約49.35〜82.25ms。固定R±1%、C±5%、VR±10%を仮定した最大は約90.34msですが、IC係数、MLCCのDCバイアス・温度特性は含みません。100ms以下の保証値ではありません。'),
 para('VRの2番（摺動端子）と3番を接続しています。摺動接点だけが離れた場合は全抵抗側へ戻る構成です。抵抗体や配線自体の断線、全故障に対する保護を保証するものではありません。'),
]
build(intro,story)
assembly_path=REVIEW/(NAME+'_assembly.pdf')
writer=PdfWriter();writer.append(str(intro));writer.append(str(REVIEW/'assembly-top.pdf'))
writer.add_metadata({'/Title':'TC IO Rev C - 組立図・接続案内'})
with assembly_path.open('wb') as f:writer.write(f)
intro.unlink()
schematic_path=REVIEW/(NAME+'_schematic.pdf');shutil.copy2(REVIEW/'schematic.pdf',schematic_path)

cover=REVIEW/'document-cover.pdf'
board_sha=hashlib.sha256((SRC/(NAME+'.kicad_pcb')).read_bytes()).hexdigest()
doc_paths=[schematic_path,bom_path,assembly_path]
counts=[len(PdfReader(p).pages) for p in doc_paths]
build(cover,[para('路面電車 運行管理','title'),para('TC IO Rev C　回路図・部品表・組立図','heading'),
 para('100 × 100 mm / 2層 / Raspberry Pi 4 Model B用 制御基板'),Spacer(1,8*mm),
 table(['資料','ページ数','内容'],[
  ['回路図',counts[0],'A1のベクター図面。画面で拡大して閲覧。'],
  ['部品表',counts[1],'基板実装50点、接続用電線・外部機器の一覧。'],
  ['組立図',counts[2],'組立順・接続表・VR調整と、部品面から見た配置図。'],
 ],[35,20,131]),Spacer(1,10*mm),
 para('実機未検証の試作版です。8センサ入力と4系統のパルス制御を搭載し、DRV8871の完成モジュール、12V負荷電源、実物センサは基板外に接続します。'),
 para('全50点を表面実装（VRを含む）とし、コネクタ部品は使いません。在庫、LCSCコード、実装対応、位置・回転は未確認で、現在のBOM/CPLは発注不可の草案です。'),
 para('固定パルスの旧Rev Bとは区別してください。本資料はVRを4個追加した100×100mmのRev Cから出力しています。'),
 para('基板ソースSHA-256','heading'),para(board_sha),
])
combined=REVIEW/(NAME+'_documents.pdf')
writer=PdfWriter();writer.append(str(cover))
for path,title in zip(doc_paths,['回路図','部品表','組立図・接続案内']):writer.append(str(path),outline_item=title)
writer.add_metadata({'/Title':'TC IO Rev C - 回路図・部品表・組立図','/Author':'Train_control'})
with combined.open('wb') as f:writer.write(f)
cover.unlink()
report={'board':NAME,'pcba_order_ready':False,'board_source_sha256':board_sha,'bom_source_sha256':hashlib.sha256((SRC/'BOM_hand_assembly.csv').read_bytes()).hexdigest(),
        'grouped_components':len(groups),'board_component_quantity':50,'unpopulated_wire_groups':21,
        'font_source':FONT_URL,'pdfs':{}}
for path in [*doc_paths,combined]:
    reader=PdfReader(path);assert not reader.is_encrypted and len(reader.pages)>0
    report['pdfs'][path.name]={'pages':len(reader.pages),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    print(path.name,len(reader.pages),'pages')
assert len(PdfReader(combined).pages)==1+sum(counts)
(ROOT/'reports/pdf-documents.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
