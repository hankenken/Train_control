# LattePanda 3 Delta 864・Windows 10で試す

Windows 10 x64、Python 3.12 x64、ネット接続を用意します。
画像処理と操作画面はLattePanda本体内で動きます。最初のデモには実カメラは不要です。

ZIPを展開し、中にcamera_controlフォルダが見える場所でPowerShellを開きます。
次を順に実行します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\camera_control\scripts\setup_windows.ps1
.\.venv-camera\Scripts\python.exe -m camera_control.app --mode demo
```

最初のコマンドはWindowsとPythonを確認し、フォルダ内の仮想環境に必要なソフトを導入します。
Python自体のインストール・Windowsの更新・管理者操作・Arduino書込みは行いません。
ExecutionPolicyはこのプロセスだけの指定で、恒久設定を変更しません。

ChromeまたはEdgeで http://127.0.0.1:8000 を開きます。
4個の模擬車両と、A/Bによる2方式の進路選択を確認できます。終了は端末でCtrl+Cです。
次回は camera_control\START_DEMO.cmd をダブルクリックしてもデモを起動できます。

## USBカメラへ進むとき

使用するのはWindows 10対応USB UVCカメラです。カメラはまず1台で画角と写りを確認します。
機器番号・画像サイズ・担当範囲を設定してから2台を接続し、実車のいない背景とA/B領域を登録します。
手順は camera_control/README_LATTEPANDA.md を参照してください。

## ポイント通信

内蔵ATmega32U4へのUSBシリアル→I2C→DRV8235×4という構成案です。
モータードライバIC自体がI2C制御に対応します。GPIO入力式DRV8871を選定した構成ではありません。
現在のカメラソフトは模擬要求を記録する段階で、実機出力・COM接続・ファームウェアは未実装です。
回路・通信・波形試験が必要なため、このZIPだけでポイントは動きません。
詳細は camera_control/output_bridge/README.md を参照してください。
