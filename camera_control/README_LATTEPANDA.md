# LattePanda 3 Delta 864・Windows 10版 カメラ進路選択

使用するOSはユーザー指定の **Windows 10 x64**、本体は **LattePanda 3 Delta 864** です。カメラ2台の取得、画像処理、進路選択、ブラウザ表示をこの本体内で行います。

**現在はシミュレーション専用です。ポイント・信号・線路電源・GPIO・Arduinoは操作しません。** 進路要求を画面とイベントに記録する試作で、運転・停止・発車はすべて手動です。

## 構成と撮影条件

- LattePanda 3 Delta 864、メーカーに適合する電源と冷却。
- Windows 10 x64と、Python 3.12 x64。セットアップは既存のPython 3.10〜3.12 x64にも対応します。
- **USB UVCカメラ×2**。購入型番、レンズ、Windows用ドライバ、2台同時動作はまだ確定していません。
- Raspberry Pi Camera Module 3 WideはCSIカメラです。LattePandaのUSBへ直接接続することはできず、今回のUSBカメラの代わりとして扱いません。
- 対象は約1m×1m、撮影高さ約50cm、同時に最大4編成という設計条件。処理できる性能や識別精度を実機で保証した値ではありません。

2台で上半分／下半分を分担する案です。購入前に、**実際に使用する解像度で水平画角およそ102°・垂直画角およそ67°を確保できるか**確認します。

理想的な真下向き投影では、高さ50cmで水平102°は幅約1.23m、垂直67°は高さ約0.66mに相当します。実際はレンズ歪み、車両の高さ、取付角度、画像のクロップで変わります。「対角120°」などの対角画角を水平・垂直画角へそのまま読み替えないでください。

各カメラが担当する線路とA/B位置、パンタグラフや架線柱による遮蔽を実映像で確認します。1920×1080を取得できても、そのモードで全画角が得られるとは限りません。

## 1. Pythonとプロジェクトを用意

Windows用のPython 3.12 **64-bit**をpython.orgから手動でインストールします。Python Launcher（`py`）を使える状態にしてください。セットアップスクリプトはPythonのインストーラをダウンロードしたり、Storeを自動起動したりしません。

リポジトリを展開した`Train_control`フォルダでPowerShellを開きます。以下はPowerShell用コマンドです。

```powershell
py -3.12 --version
powershell -NoProfile -ExecutionPolicy Bypass -File .\camera_control\scripts\setup_windows.ps1 -CheckOnly
powershell -NoProfile -ExecutionPolicy Bypass -File .\camera_control\scripts\setup_windows.ps1
```

`-ExecutionPolicy Bypass`はこのPowerShellプロセスだけの指定で、永続設定を変更しません。管理者として起動する必要はありません。組織のポリシーで実行できない場合は、その管理方針に従ってください。

スクリプトはWindows 10 x64とPythonを**先に確認**し、合わなければ環境作成前に終了します。本体がLattePandaかどうかは自動判定せず、実機の型式を人が確認します。

`.venv-camera`を作成し、その中だけに`requirements-windows.txt`のFastAPI・Uvicorn・NumPy・OpenCVをpipで導入します。Picamera2やLinux用パッケージは導入しません。既存フォルダが他OSの仮想環境等だった場合は上書きせず停止します。別の保存先は`-VenvPath`で指定できます。

サービス登録、自動起動設定、再起動、ファームウェア更新、Arduinoへの書込み、シリアル接続は行いません。

### 手動で導入する場合

上記スクリプトと同じ環境を手動で作る場合は、Windows 10 x64・Python x64を確認してから次を実行します。既存の同名フォルダを削除する必要はありません。別OSの環境がある場合は別名を使い、後続のPythonパスも揃えます。

```powershell
py -3.12 -m venv .venv-camera
.\.venv-camera\Scripts\python.exe -m pip install -r .\camera_control\requirements-windows.txt
.\.venv-camera\Scripts\python.exe -c "import cv2,numpy,fastapi,uvicorn; print('dependencies OK')"
```

`Activate.ps1`の実行は不要です。以降も仮想環境のPythonを直接指定するので、PowerShellの永続ポリシーを変更する必要はありません。

## 2. USBカメラ2台を確認

カメラのメーカーが対応を明記するUSBポートとケーブルを使います。まずは本体のUSB 3対応ポートへ分散して接続し、不要なハブを避けて試します。別ソケットでも同じ内部USB経路を共有する場合があるため、2台同時の帯域と電力は実機で確認します。

Windowsの「設定→プライバシー→カメラ」で、このデバイスのカメラアクセスとデスクトップアプリからのアクセスが許可されていることを確認します。カメラを使う他のアプリは閉じます。

次のコマンドは**カメラを開きません**。対応OSと次の操作を表示するだけです。

```powershell
.\.venv-camera\Scripts\python.exe .\camera_control\scripts\check_usb_cameras.py
```

次は候補インデックスを順番に開く検査です。カメラのランプが点灯する場合があります。DirectShowを初期バックエンドにします。

```powershell
.\.venv-camera\Scripts\python.exe .\camera_control\scripts\check_usb_cameras.py --probe --indices 0,1,2,3,4 --backend dshow
```

WindowsのカメラインデックスはUSB差し替えや再起動で変わることがあります。番号0と1が別の物理カメラであることも、この検査だけでは保証しません。実際の映像で片方の前を手で遮るなどして、担当するカメラを人が確認してください。

使用する2つの番号を確認できたら、同時に開く試験を行います。

```powershell
.\.venv-camera\Scripts\python.exe .\camera_control\scripts\check_usb_cameras.py --capture-test --devices 0,1 --backend dshow --capture-size 1920x1080 --fps 15 --fourcc MJPG
```

各3フレームを受信し、実フレームサイズ、ドライバが報告するfps・FOURCC、読取り時間を表示してカメラを解放します。画像は保存しません。`--devices`には選定した異なる2番号を必ず指定します。

- `requested`は設定要求、`reported_*`はドライバ報告値です。設定要求が受理されても実際のサイズ・速度とは限りません。
- `actual_size`は受信した画像のサイズです。要求と異なる場合は、設定や対応モードを確認します。
- `reported_fps`は実測fpsではありません。この短い検査で2台同時処理の速度を保証しません。
- フレーム時刻は**ホストでreadが完了した時刻**です。撮像素子の露光時刻ではなく、USB・ドライバのバッファ遅延を含みます。
- MJPGに対応しないカメラでは別の対応形式を指定します。DirectShowで動作しない場合は`--backend msmf`を試し、アプリ設定の`backend`も同じ方式へ揃えます。

## 3. デモを表示

```powershell
.\.venv-camera\Scripts\python.exe -m camera_control.app --mode demo --config .\camera_control\config\demo.json --host 127.0.0.1 --port 8000
```

LattePanda上のChromeまたはEdgeで **http://127.0.0.1:8000** を開きます。終了はPowerShellでCtrl+Cです。Windowsのカメラをまだ接続していなくても、デモは合成映像で確認できます。

デモの車両やA/B線は例です。デモの判定成功を実カメラの校正・動作保証として扱いません。

## 4. 実USBカメラの設定と起動

```powershell
Copy-Item .\camera_control\config\lattepanda.example.json .\camera_control\config\lattepanda.local.json
notepad .\camera_control\config\lattepanda.local.json
```

各カメラの`device`へ、確認したWindowsインデックスを指定します。設定例の0／1は実機の認識結果ではありません。

```json
{
  "id": "cam0",
  "device": 0,
  "backend": "dshow",
  "capture_size": [1920, 1080],
  "processing_size": [1280, 720],
  "fps": 15,
  "fourcc": "MJPG"
}
```

2台目は`id: "cam1"`とし、異なる確認済み`device`番号を設定します。カメラ固有の露出・フォーカス制御は、この例だけで校正済みにはなりません。

```powershell
.\.venv-camera\Scripts\python.exe -m camera_control.app --mode usb --config .\camera_control\config\lattepanda.local.json --host 127.0.0.1 --port 8000
```

初期の`vision.lanes`は空です。映像を見て、実際の線区・A/B線・進行方向を設定するまで進路判定を開始しません。`outputs_enabled`は`false`のまま使います。

### 線区とA/B位置

座標は表示用640×360ではなく、**`processing_size`の画素座標**で指定します。1280×720の例を使う場合、A/B線や線路を囲む領域もその画像に合わせます。

`vision.lanes`の各項目には、`id`、`camera`、`polygon`、`gate_a`、`gate_b`、`direction`を指定します。`id`は`routes.lanes`と一致させ、方式・時間は`routes.lanes`で設定します。4線区のIDは`upper_outer`・`upper_inner`・`lower_outer`・`lower_inner`です。

デモ設定は構造の例として参照できますが、座標をそのまま実カメラに流用しません。USBカメラの解像度・クロップ・カメラ位置を変えたときはA/B領域と背景も見直します。

## 5. 背景登録と手動操作

1. 2台の映像と物理カメラの対応、ピント・露出、担当範囲が正しいか確認します。
2. 実映像でJSONへ線区とA/B線を登録し、アプリを再起動します。
3. **各撮影範囲から車両をすべて取り除いてから**、画面の確認チェックを入れて「空の背景を登録」を押します。背景登録でA/B位置が自動作成されることはありません。
4. 1編成・低速から手動で試し、検出領域、車両ID、A→Bの判定を確認します。
5. 進路確定後はロックされます。**編成全体が通過したことを人が確認**し、チェックを入れてロック解除します。

「検出を一時停止」は画像処理を止める操作です。列車や線路電源を停止しません。A検出・LED相当表示・解除から実機出力は発生しません。

## 試作の限界と確認範囲

- 車両IDは担当カメラ・線区内での位置追跡用です。カメラ間の引継ぎ、レイアウト全体での再識別、編成全体のグループ化は未実装です。
- 同じ見た目の車両、接近、交差、遮蔽による対応の曖昧さは解決済みではありません。不確かな状態では保留し、人が確認します。
- A/B通過は検出領域の重心が線を横切ることによる判定で、先頭・最後尾の検出ではありません。最後尾通過を自動判定してロック解除しません。
- USBカメラの時刻はホスト受信完了時刻です。厳密な露光時刻ではなく、2台の同期撮影も保証しません。
- 1920×1080・15fps×2は初期の要求値です。実カメラの画角、フレーム落ち、USB帯域、処理時間、温度、ブラウザ配信を含めて本体上で測定します。
- クラウドでのデモ／録画確認と、LattePanda 3 Delta・Windows 10・USBカメラ2台の実機試験は別です。実機の連続稼働・速度・識別精度は未検証です。

LattePanda内蔵ATmega32U4を将来のパルス出力に使うことは別途検討できますが、現在の試作にはそのファームウェア・通信・実機出力機能はありません。

Windows 10通常版の通常サポートは2025年10月14日に終了しています。ESU・LTSC等は版や契約により異なるため、使用環境の更新条件を確認してください。今回は指定どおりWindows 10で進めます。

## 購入費用・通信ドライバ

[購入を抑える機材案](docs/lattepanda-budget.md)と[数量・予算目標CSV](docs/lattepanda-equipment.csv)を用意しました。
ポイントは[内蔵USBシリアル→ATmega→DRV8235のI2C](output_bridge/README.md)構成を候補にします。IC自体がI2C制御に対応します。回路・ファームウェアは未実装です。

[USBカメラの配置条件例](docs/lattepanda-camera-placement.svg)。この図の画角は選定条件の例で、購入済みカメラの実測値ではありません。
