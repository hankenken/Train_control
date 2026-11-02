# TC2 USBシリアル仕様 — DRV8235 I2C試作

ファームウェアと独立したPython試験クライアントを実装しています。クラウドでのコンパイル・状態遷移試験までで、実機通信・波形は未検証です。カメラアプリには接続しません。

## フレーム

115200指定のUSB CDC、ASCII、LF終端、終端のCRを許容。改行を除き63バイトまで。USBの実転送速度を115200bpsで保証するものではありません。
起動時はDISARMED、D4/D5 LOW。USB待ちで処理を止めません。新しい接続だけでARMしません。

```text
HELLO
READY TC2 DRV8235_I2C
STATUS
STATUS TC2 DRV8235_I2C armed=0 active=-1 last_seq=0 hb_age_ms=-1 fault=NONE vm_ready=0 pending=0
```

HELLOとSTATUSは読取り専用。出力、時刻、seq、故障を変更しません。`active=-1`は非駆動、`pending=1`はARM/PULSEの単発準備中、`vm_ready=1`はMCU起動後のVM電源入れ直しを観測した状態です。

| コマンド | 意味 | 応答 |
|---|---|---|
| `HB <seq>` | 生存時刻だけを更新 | `OK <seq> HB` |
| `ARM <seq>` | 新鮮なHB・VMリセット観測・故障なしで、全4個をウェイク・設定・読戻し。出力は禁止のまま論理ARM | `OK <seq> ARM` |
| `PULSE <seq> <ch> <P/N> <ms>` | 明示ARM済み、ch=0..3、20..100msで単発1系統 | `OK <seq> PULSE` |
| `STOP <seq>` | D4を即LOW、準備・単発を取消し、DISARM | `OK <seq> STOP` |

`seq`は1..4294967295の十進整数で単調増加。正しい構文の新しいコマンドは拒否時も番号を消費します。同じ番号をPULSE再試行に使いません。古い番号は`ERR <seq> STALE`。STOPは古い／構文不正でも、認識できた時点で禁止を先に実行します。

ARM/PULSEは前のハードウェア単発QがLOWに戻るのを待つため、応答は即時とは限りません。準備の待ち期限300ms、ウェイク待ち1ms、設定所要上限40ms。ホストのACK待ちは1秒を初期値とします。待機中もHB/STOPの受信処理を続けます。

## チャンネルとパルス

| ch | 7bit I2C | 線区 |
|---:|---|---|
| 0 | 0x30 | upper_outer |
| 1 | 0x32 | upper_inner |
| 2 | 0x36 | lower_outer |
| 3 | 0x38 | lower_inner |

P=OUT1→OUT2、N=逆極性。青白と直／曲の対応は実測して決めます。
全4個の設定を読戻した後、対象だけEN_OUTを有効化。通常終了はEN_OUT=0とOFF=00の読戻し後にD4 LOWとし、`DONE <seq> <ch>`を返します。中断・エラーではDONEを返しません。OKもDONEも機械位置や列車通過を証明しません。

同時1系統、前回終了から各系統1秒の初期クールダウン。駆動中の新要求はBUSY、同系統の短時間再要求はCOOLDOWNで拒否し、元のパルスを延長しません。1秒はメーカー保証の熱条件ではありません。

時間はMCUの符号なしmillis差分で管理します。I2Cの有限処理・ループの遅延があるため、実電圧パルスが設定msと厳密に一致する保証はありません。Windowsのsleepで通電終了を管理しません。

## 異常と復旧

- HB初期間隔100ms、500ms以上古くなれば、ARM／準備／駆動中はD4 LOW・故障ラッチ。
- USB DTR喪失、VM低下、nFAULT、I2C失敗、設定不一致、ハードウェア単発Q切れも禁止・故障ラッチ。
- 不正な行や範囲外は`ERR 0 MALFORMED`。63バイトを超えた時点で禁止し、次の改行まで破棄して`ERR 0 LINE_TOO_LONG`。残りを別命令にしません。
- 故障はSTOP、HB、HELLO、STATUSでも解除しません。MCU再起動と、**その後のVM電源入れ直し**が必要です。再開には再度明示ARMが必要。
- VM観測の初期条件はA0のADC≤5を100ms→ADC≥150を100ms。分圧・5V基準の回路が必要。VM未リセットは`VM_RESET_REQUIRED`でARMを拒否。
- 終了ACK/DONEが失われても**PULSEを自動再送しません**。新しいseqのSTOPを1回だけ試み、故障として接続を終了します。seq最大値なら古いSTOPでも禁止を優先させます。

主なERR理由：STALE / BUSY / COOLDOWN / DISARMED / VM_RESET_REQUIRED / HEARTBEAT_TIMEOUT / USB_LOST / VM_LOST / DRIVER_FAULT / I2C_FAULT / CONFIG_MISMATCH / UNEXPECTED_ENABLED / CONFIG_TOO_SLOW / GATE_MISSING / GATE_TIMEOUT / MALFORMED / LINE_TOO_LONG / SERIAL_TX。

USB切断などの非同期故障はSTATUSで確認します。STOPでの取消しはI2C終了読戻しに依存せず、D4 LOWを優先します。その後に再ウェイクするには上記の復旧条件が必要です。

## 独立した禁止経路

D4と、CD74HC221の単発Qと、5V POWER_GOODのANDを全nSLEEPへ接続します。単発はR620k/C470nFの公称約204ms、**未測定であり100msの独立上限保証ではありません**。D6の読戻しだけを固定HIGHで代用しません。
MCUの約60msウォッチドッグと2ms Wireタイムアウトも使います。ウォッチドッグの実時間・ブートローダ復帰・USBドライバ・I2Cハング・nSLEEPによる回生条件は実機試験が必要です。
