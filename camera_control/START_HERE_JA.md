> 旧Pi版の手順です。現在のLattePanda・Windows10版は [START_HERE_WIN10_JA.md](START_HERE_WIN10_JA.md) を参照してください。

# Raspberry Pi 5で試す

必要：Raspberry Pi 5、64-bit Raspberry Pi OS、ネット接続、モニタ・キーボード・マウス。
最初のデモには実カメラは不要です。撮影確認へ進むときにCamera Module 3 Wideを2台接続します。

ZIPを展開したフォルダ（中にcamera_controlフォルダが見える場所）で端末を開きます。
次を順に実行します。初回の導入ではsudoの確認やパスワード入力が必要になる場合があります。

```bash
bash camera_control/scripts/setup_pi.sh
.venv-camera/bin/python -m camera_control.app --mode demo
```

Piのブラウザで http://127.0.0.1:8000 を開きます。
4個の模擬車両、A/Bの仮想線、時間差方式とLED方式の選択を確認できます。
端末を開いたまま使い、終了するときは端末でCtrl+Cを押します。

このソフトはポイント・信号・車両電源を操作しません。実出力をONにする機能はありません。
模擬車両が画面から出ても、ロックは自動で解除されません。通過状態を確認して画面で解除します。

実機用の手順・必要機材・カメラ配置は camera_control/README.md を参照してください。
カメラ2台での画角・ピント・処理速度、実車の検知はPi実機でこれから確認します。
