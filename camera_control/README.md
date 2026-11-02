> 現在の指定は **LattePanda 3 Delta 864＋Windows 10**です。[現在の導入手順](README_LATTEPANDA.md)を参照してください。以下は旧Pi版の保存資料です。

# Raspberry Pi内で動かすカメラ進路選択・試作

Raspberry Pi 5（8GB）とCamera Module 3 Wideを2台使用し、撮影から検出・進路選択・ブラウザ表示までPi内で実行する構成です。Windowsはブラウザで表示する端末として使えます。

**現段階はシミュレーション専用です。GPIO出力・ポイント駆動・信号灯・線路給電を制御する機能はありません。** 進路確定は画面とイベントへの模擬要求として記録します。列車の速度・停止・発車は手動です。

- 時間差方式：AからBまでの時間で進路を選択。
- LED相当表示方式：Aで交互表示を開始し、Bのタイミングで進路を選択。
- A検出・LED相当表示・解除では進路要求を発生させません。
- 編成全体の通過を人が確認した後にロックを解除します。
- 識別が不確かな場合は判定保留として表示します。実機の安全な進路制御を保証する装置ではありません。

## 必要な機器

- Raspberry Pi 5 8GB、適合するUSB-C電源、冷却装置、Raspberry Pi OS 64-bit（BookwormまたはTrixie）。
- Raspberry Pi Camera Module 3 Wide ×2。
- **カメラ用15ピン→22ピンの変換フラットケーブル×2**。Camera Module 3側とPi 5側で端子幅が異なります。
- Pi 5のCAM/DISP 0・1へ接続。HDMIやUSBのソケットには接続しません。向きはPiとカメラの公式取付図で確認し、電源を切って作業してください。

Wideの画角でもレイアウト全体が必ず撮れるとは限りません。各カメラの撮影高さ・レンズ位置・車両の大きさを実映像で確認します。複線の車両や交差部分が重なって見える場合、カメラの位置から見直します。

## Piのセットアップ

リポジトリのルート `Train_control` で実行します。セットアップはPi 5・64-bit・Raspberry Pi OSを先に確認し、条件に合わなければインストール前に終了します。

```bash
bash camera_control/scripts/setup_pi.sh --check-only
bash camera_control/scripts/setup_pi.sh
```

スクリプトはaptで `python3-picamera2`、`python3-opencv`、`python3-numpy`、`python3-venv`、`rpicam-apps`を導入し、`.venv-camera`を `--system-site-packages` で作成します。pipではFastAPIとUvicornだけを導入します。

**Piではpipのopencv-pythonやopencv-python-headlessでaptのcv2を置き換えないでください。** Picamera2・libcamera・NumPyをOSパッケージで揃えます。スクリプトはサービス登録・自動起動・再起動を行いません。

作成先を変える場合は `--venv /希望のパス` を指定し、以下のコマンドもそのPythonのパスへ読み替えます。

### Piで手動インストールする場合

自動セットアップと同じ構成を手動で用意する場合は、Pi 5上のRaspberry Pi OS 64-bitで次を実行します。

```bash
sudo apt-get update
sudo apt-get install -y python3-picamera2 python3-opencv python3-numpy python3-venv rpicam-apps
python3 -m venv --system-site-packages .venv-camera
.venv-camera/bin/python -m pip install -r camera_control/requirements.txt
```

開発用のLinux PC・クラウドでデモ／録画だけを確認する場合は、Piの環境とは分けた仮想環境で依存関係を導入できます。**次のコマンドはPi用ではありません。** Picamera2と実カメラは使用しません。

```bash
python3 -m venv /tmp/train-camera-demo
/tmp/train-camera-demo/bin/python -m pip install -r camera_control/requirements.txt numpy opencv-python-headless
/tmp/train-camera-demo/bin/python -m camera_control.app --mode demo --config camera_control/config/demo.json --host 127.0.0.1 --port 8000
```

## カメラ2台の確認

```bash
rpicam-hello --list-cameras
.venv-camera/bin/python camera_control/scripts/check_cameras.py
```

`check_cameras.py`はセンサ名・インデックス・センサモード・クロップ範囲をJSONで表示します。Picamera2はPi 5であることを確認してから読み込みます。PCで実行すると「非対応プラットフォーム」として終了し、カメラやGPIOを操作しません。

必要なら次のコマンドで2台を同時に開始し、各1フレームだけ取得して終了します。画像は保存しません。

```bash
.venv-camera/bin/python camera_control/scripts/check_cameras.py --capture-test
```

この試験の640×360・10fpsは要求値で、処理速度の保証ではありません。センサモードのfpsも、2台同時撮影・画像処理・配信を含む実測値ではありません。出力解像度だけで全画角を取得できるとは判断せず、実際の`ScalerCrop`と線路の写り方を確認します。

## デモで起動

```bash
.venv-camera/bin/python -m camera_control.app --mode demo --config camera_control/config/demo.json --host 127.0.0.1 --port 8000
```

Piのブラウザで `http://127.0.0.1:8000` を開きます。終了は起動したターミナルでCtrl+Cです。

デモのカメラ・車両・線区・A/B線は合成した例です。デモの背景登録や判定結果を実カメラの校正済み状態として扱いません。

## 実カメラで起動

まず設定例を自分用にコピーします。

```bash
cp camera_control/config/pi5.example.json camera_control/config/pi5.local.json
.venv-camera/bin/python -m camera_control.app --mode pi --config camera_control/config/pi5.local.json --host 127.0.0.1 --port 8000
```

Pi用の設定例では、実際の線路位置を推測で決めないよう **`vision.lanes`を空**にしています。映像が出ても、A/B線と線区を設定するまでは検出できません。4系統の進路表示と、撮影範囲の登録は別です。

1. 2台の映像が更新されていることを確認します。カメラの`index`は実際の列挙結果に合わせます。
2. 車両を置き、全線路が映るか、ピントが合うか、重なりで見失わないかを確認します。AFを固定する場合は`controls`の`AfMode`・`LensPosition`を実際の設置距離に合わせます。例の数値は校正結果ではありません。
3. 下記の方法で設定JSONへ線区の領域と仮想A/B線を登録し、サーバーを再起動します。
4. **各カメラの範囲から全車両を取り除いてから**、画面の「この映像の範囲に車両がいないことを確認」をチェックし、「空の背景を登録」を押します。背景登録はA/B線の設定を作る操作ではありません。
5. 1編成・低速・手動運転から試し、誤検出、遮蔽、停止中、再発車時のIDと進路を確認します。

現在は出力を有効にするスイッチやエンドポイントはありません。`outputs_enabled`は`false`のまま使用します。

### 仮想A/B線と線区の登録

- `cameras[].processing_size`が画像処理の座標系です。Pi例は1280×720、表示用プレビューは640×360です。
- `vision.lanes[].polygon`：同じ線路を囲む領域。複線は別の領域にします。
- `gate_a`・`gate_b`：それぞれ2点で指定する仮想線です。進行方向にA→Bとなるよう配置します。
- `direction`：その領域での進行方向ベクトル。
- `camera`：`cam0`または`cam1`。両カメラで同じ場所を扱う場合も、IDの対応は自動的に保証されません。
- `id`：`routes.lanes[].id`と一致させます。既定は`upper_outer`、`upper_inner`、`lower_outer`、`lower_inner`です。
- 時間差方式は`mode: "time"`と`time_threshold_s`、交互表示方式は`mode: "led"`と`led_interval_s`を設定します。進路方式の設定元は`routes.lanes`です。`vision.lanes`は画像領域・A/B線・方向を設定します。

次は**構造を示す例**です。実機の1280×720設定へそのままコピーせず、実映像で測った座標へ変更してください。

```json
{
  "id": "upper_outer",
  "camera": "cam0",
  "mode": "time",
  "time_threshold_s": 2.0,
  "led_interval_s": 2.0,
  "polygon": [[15, 68], [625, 68], [625, 132], [15, 132]],
  "gate_a": [[220, 70], [220, 130]],
  "gate_b": [[430, 70], [430, 130]],
  "direction": [1, 0]
}
```

上記は640×360のデモ上の値です。プレビュー上の位置から座標を求めるときは、実際のクロップや余白を確認したうえで処理解像度との比率を使います。座標を単純に倍にするだけで、実際の線路位置が決まるわけではありません。

本試作のA/B検出は画像上の車両位置に基づきます。車体長・連結・パンタグラフ・前後車両の重なりを含め、物理接点と同じ動作になるとは保証していません。

## 録画での確認

```bash
cp camera_control/config/replay.example.json camera_control/config/replay.local.json
.venv-camera/bin/python -m camera_control.app --mode replay --config camera_control/config/replay.local.json --host 127.0.0.1 --port 8000
```

先に`cameras[].path`を自分の動画へ変更します。相対パスは設定JSONのあるフォルダが基準です。録画ごとに撮影条件・線区・背景の登録が必要です。録画の時刻と実カメラの時刻は別で、壁時計の日時として扱わないでください。

## 画面の操作

- 2つのプレビュー：表示用640×360。エラー後に映像が戻らなければ「映像を再接続」を押します。
- 「検出を一時停止／再開」：画像処理の試験用。列車や線路電源は停止しません。
- 「空の背景を登録」：確認チェック後に現在のフレームを背景として登録します。走行中や車両が写った状態では行いません。
- 「通過完了・ロック解除」：線区がロック中／判定保留で、「編成全体が通過したことを確認」をチェックした場合だけ押せます。映像の一部で先頭車が消えただけでは編成全体の通過確認になりません。
- 「現在の設定を確認」：GETで現在のJSONを表示するだけです。ここから編集はできません。

サーバー接続が切れると操作ボタンを無効化し、確認チェックを解除します。カメラ欄は取得フレーム数・取得から処理までの経過ms・処理時間ms、記録欄は「何秒前」の相対時間を表示します。取得時刻は単調増加の時計を使い、人が読む日時としては表示しません。

## 確認状況と限界

デモのコード・ブラウザ表示はクラウド／PC上で確認しています。**Pi 5と実カメラ2台での撮影・連続処理は未検証です。**

IDは割り当てたカメラと線区の中で検出位置を追跡するための仮IDです。カメラ間の引継ぎ、レイアウト全体で同一車両を再識別する機能、複数車両を編成全体としてまとめる機能はありません。同じ見た目の車両、接近・交差・遮蔽によるID対応の曖昧さは解決済みではなく、判定を保留して手動確認する対象です。自動露出、照明変化や影も検出に影響します。

A/B通過は検出領域の**重心が仮想線を横切ること**で判定します。先頭・最後尾を認識した通過検知ではありません。編成全体が線区を抜けたことは運転者が確認し、チェックを入れてロック解除します。

640×360の表示、画像処理解像度、カメラのセンサモード、取得fps、描画・ブラウザ配信の負荷を合わせてPi上で測定してください。2台・15fps等の要求値だけで性能を保証しません。

本試作は出力なしの検証段階です。実機のポイント・信号へ接続するには、通電保護、進路競合、通過確認、再起動・故障時の動作などを含む別の設計と試験が必要です。

## 配置・機材と検証結果

- [カメラ配置図](docs/camera-placement.svg)
- [必要機材一覧](docs/equipment.csv)
- [実装範囲と制約](docs/system-plan.md)
- [デモ画面](docs/demo-dashboard.png)

自動試験は `python -m unittest discover -s camera_control/tests -v`。API試験には開発用依存が必要です。
先に仮想環境で `python -m pip install -r camera_control/requirements-dev.txt` を実行してください。

デモは約30秒周期で繰り返します。車両が全て画面外へ出た空白時間に、各線区の「編成全体が通過したことを確認」をチェックしてロックを解除します。解除しないまま次の周回が来ても進路要求は自動的に更新しません。
