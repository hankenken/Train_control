#!/usr/bin/env python3
"""Export datasheet selection evidence, not fabrication drawings."""
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
root=Path(__file__).resolve().parent
pdfmetrics.registerFont(TTFont('JP','/tmp/train-pdf-fonts/NotoSansJP-400.ttf'))
s=ParagraphStyle('jp',fontName='JP',fontSize=9,leading=13,spaceAfter=7,wordWrap='CJK');sm=ParagraphStyle('small',parent=s,fontSize=8,leading=11)
def p(t):return Paragraph(escape(t),s)
def table(data,widths):
 t=Table([[Paragraph(escape(str(x)),sm) for x in r] for r in data],colWidths=[x*mm for x in widths],repeatRows=1);t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.3,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4edf0')),('VALIGN',(0,0),(-1,-1),'TOP')]));return t
story=[p('架線柱用ToFセンサ選定 — VL53L4CD優先'),p('資料照合段階／基板・部品調達・10mm実機検出は未確定'),p('ユーザー指定によりToF方式へ変更。発光・受光・処理を一体化したST VL53L4CDを第一候補とします。アナログ反射式とバッファ基板は採用対象外です。'),table([
['項目','ST DS13812 Rev8による確認'],['素子寸法','4.4×2.4×1mm。Optical LGA12。完成基板の寸法ではありません。'],['近距離','公称0〜1200mm、1mmまでの近距離直線性。1mm精度という意味ではありません。'],['電源','AVDD2.6〜3.5V、I/O1.6〜3.5V。3.3Vでの利用を検討可能。'],['端子・通信','SDA9、SCL10、XSHUT5、GPIO1=7。7bitアドレス0x29。'],['動作電流','23℃・2.8Vの既定設定条件で平均典型22mA／最大24mA、ピーク40mA/台。'],['近距離精度例','33ms・1〜100mm：白88% ±7mm室内/±8mm屋外曇天、灰17% ±6/±7mm。90%以上の測定値の品質指標。'],['局所部品','メーカー推奨例100nF＋4.7µF、XSHUT10kΩプルアップ。GPIO1未使用なら未接続可。'],['小型基板目標','約10×10mmを仮目標。4本の直付け位置と素子・容量・光学ゾーンの配置を確認して確定。']], [33,137]),p('10mmの屋根を距離値だけで絶対判定しません。車体なしの背景との差、測定有効status、ヒステリシスと連続確認を使い、黒・白・銀の屋根とパンタグラフ・照明を実機確認します。'),p('比較候補VL6180Xは4.8×2.8×1mm、電源2.6〜3.0V。素子への3.3V直結はできません。寸法と電源条件からVL53L4CDを優先。'),PageBreak(),p('8台構成・電源・確認条件'),p('8台の同時測距では、資料条件から最大平均192mA、ピーク重なりの仮定で320mA。旧アナログセンサの40mAという電源計算は流用しません。専用の安定化3.3V電源と配電・局所容量を設計し、Piの3.3V端子だけに全台を載せる構成は避けます。'),p('4線案は3.3V/GND/SDA/SCL。XSHUTは同じ電源へ10kΩでプルアップし浮かせません。GPIO1を省略する場合は公式ドライバでready/statusを確認し、timeoutと復帰手段を実装。DNC8番はGNDにもつながず未接続。'),table([['VL53L4CDピン','機能'],['1/11','AVDDVCSEL / AVDD →電源'],['2/3/4/6/12','AVSSVCSEL / GND / GND2 / GND3 / GND4 → GND'],['5','XSHUT、LOW有効。電源ON時のみHIGH'],['7','GPIO1、オープンドレインready割込み'],['8','DNC、必ず未接続'],['9/10','SDA / SCL']], [37,133]),p('STの端子図は底面図です。LGAの上面図・ランド・実装モデルの向きへの変換が必要。まだ基板CADを作成・承認した段階ではありません。'),p('TI TCA9548Aを8チャネルスイッチの候補とします。1.65〜5.5V、最大400kHz。A0/A1/A2=GNDで7bit0x70。読出し時は1チャネルだけ選び、同アドレス0x29を分離します。VL53L4CDの1MHz能力をそのまま8台構成へ適用しません。'),p('I2Cを分離してもレーザーの発光・測距は停止しません。同時測距の光学干渉を実機で確認。33msずつ8台を直列測距すれば通信を除いて約264ms/巡回となり、各台100Hzにはなりません。連続測距と順次読出し、A/B優先処理、遮光の評価が必要です。'),p('公式資料：ST DS13812 Rev8（1/3/4/5/17/18/20ページ）、ST VL6180X DocID026171 Rev7、TI TCA9548A SCPS207H。原本PDFとSHA-256はreference/とselection.jsonへ保存。')]
SimpleDocTemplate(str(root/'ToF_sensor_selection_DRAFT.pdf'),pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,topMargin=16*mm,bottomMargin=16*mm).build(story)
print('ToF selection summary PDF written')
