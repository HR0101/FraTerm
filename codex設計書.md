```markdown
<!-- File: PLAN.md -->

# ターミナル動画プレイヤー開発計画書

## 1. プロジェクト概要

動画ファイルを文字またはANSIカラーへ変換し、ターミナル上で再生するCLIソフトウェアを開発する。

動画ごとに名前と再生設定を登録し、登録後はファイルパスを入力せず、短いコマンドで再生できるようにする。

```text
termvid add badapple ./videos/bad-apple.mp4 --mode ascii
termvid badapple
```

## 2. プロジェクト名

仮称:

```text
termvid
```

正式名称は開発中に変更できるものとする。

## 3. 開発目的

- ターミナルだけで動画を再生できるようにする
- 動画をASCII文字やANSIカラーで表現する
- 動画ごとの再生設定を保存できるようにする
- 登録名だけで簡単に動画を呼び出せるようにする
- Linux、macOS、Windowsで利用できるCLIツールを目指す

## 4. 想定利用者

- ターミナル上の表現を楽しみたい利用者
- ASCIIアートやANSIアートに興味がある利用者
- CLIソフトウェアを日常的に使用する開発者
- ターミナルを使った演出やデモを行いたい利用者

## 5. 主要機能

### 5.1 動画再生

動画ファイルを読み込み、フレーム単位でターミナルへ描画する。

対応予定の描画方式:

| モード | 内容 |
|---|---|
| `ascii` | 明るさをASCII文字へ変換する |
| `color` | ANSI True Colorとブロック文字でカラー表示する |
| `mono` |白黒のブロック文字で表示する |

初期バージョンでは、`ascii`と`color`を実装する。

### 5.2 動画登録

動画に任意の登録名を付け、動画ファイルの場所と再生設定を保存する。

```bash
termvid add neko ~/Videos/cat.mp4 --mode color --audio
```

保存する情報:

- 登録名
- 動画ファイルの絶対パス
- 描画モード
- 音声再生の有無
- 文字セット
- 明るさ
- コントラスト
- 最大横幅
- FPS制限

### 5.3 登録名による再生

登録後は、登録名だけで動画を再生できるようにする。

```bash
termvid neko
```

明示的な再生コマンドも用意する。

```bash
termvid play neko
```

### 5.4 登録一覧

登録されている動画と設定を一覧表示する。

```bash
termvid list
```

表示例:

```text
NAME      MODE    AUDIO  VIDEO
badapple  ascii   no     /home/user/Videos/bad-apple.mp4
neko      color   yes    /home/user/Videos/cat.mp4
```

### 5.5 登録内容の確認

指定した動画の詳細な設定を表示する。

```bash
termvid show neko
```

### 5.6 登録内容の変更

登録済み動画の設定を変更できるようにする。

```bash
termvid edit neko --mode ascii --no-audio
```

初期バージョンでは、同じ名前で再登録する方法でも対応可能とする。

```bash
termvid add neko ~/Videos/cat.mp4 --mode ascii --force
```

### 5.7 登録削除

登録情報を削除する。

```bash
termvid remove neko
```

動画ファイル自体は削除しない。

### 5.8 音声再生

FFmpegに含まれる`ffplay`を利用し、映像と同時に音声を再生する。

```bash
termvid add opening ~/Videos/opening.mp4 --mode color --audio
termvid opening
```

### 5.9 再生操作

再生中に以下の操作を受け付ける。

| キー | 操作 |
|---|---|
| `q` | 再生終了 |
| `Space` | 一時停止・再開 |
| `r` | 最初から再生 |
| `m` | ミュート切り替え |
| `+` | 再生速度を上げる |
| `-` | 再生速度を下げる |

初期バージョンでは、`q`による終了を必須機能とする。

## 6. コマンド仕様

### 6.1 動画の登録

```bash
termvid add <登録名> <動画ファイル> [オプション]
```

使用例:

```bash
termvid add badapple ./bad-apple.mp4 --mode ascii
```

主なオプション:

| オプション | 内容 |
|---|---|
| `--mode ascii` | ASCII文字で表示する |
| `--mode color` | ANSIカラーで表示する |
| `--audio` | 音声を再生する |
| `--no-audio` | 音声を再生しない |
| `--width <数値>` | 最大表示幅を指定する |
| `--fps <数値>` | 最大FPSを指定する |
| `--charset <文字列>` | ASCII変換に使用する文字を指定する |
| `--force` | 同名の登録を上書きする |

### 6.2 動画の再生

```bash
termvid <登録名>
```

または次の形式を使用する。

```bash
termvid play <登録名>
```

### 6.3 登録一覧

```bash
termvid list
```

### 6.4 登録詳細

```bash
termvid show <登録名>
```

### 6.5 登録変更

```bash
termvid edit <登録名> [オプション]
```

### 6.6 登録削除

```bash
termvid remove <登録名>
```

### 6.7 ファイルを直接再生

登録せずに動画ファイルを直接再生する機能も用意する。

```bash
termvid run ./videos/sample.mp4 --mode color
```

### 6.8 ヘルプ表示

```bash
termvid --help
```

```bash
termvid add --help
```

## 7. 設定データ

### 7.1 保存内容

登録情報はJSONファイルへ保存する。

```json
{
  "badapple": {
    "path": "/home/user/Videos/bad-apple.mp4",
    "mode": "ascii",
    "audio": false,
    "width": null,
    "fps": null,
    "charset": " .,:;irsXA253hMHGS#9B&@"
  },
  "neko": {
    "path": "/home/user/Videos/cat.mp4",
    "mode": "color",
    "audio": true,
    "width": 100,
    "fps": 30,
    "charset": null
  }
}
```

### 7.2 保存場所

OSごとに適切な設定ディレクトリを使用する。

| OS | 保存場所 |
|---|---|
| Linux | `~/.config/termvid/videos.json` |
| macOS | `~/Library/Application Support/termvid/videos.json` |
| Windows | `%APPDATA%\termvid\videos.json` |

### 7.3 動画ファイルの扱い

初期バージョンでは動画ファイルをコピーせず、絶対パスのみを保存する。

登録後に動画ファイルが移動または削除された場合は、再生時にエラーを表示する。

将来的には、動画を専用ライブラリへコピーする機能を追加できる。

```bash
termvid add neko ./cat.mp4 --copy
```

## 8. システム構成

```text
termvid/
├── pyproject.toml
├── README.md
├── PLAN.md
├── LICENSE
├── termvid/
│   ├── __init__.py
│   ├── cli.py
│   ├── player.py
│   ├── renderer.py
│   ├── registry.py
│   ├── audio.py
│   ├── keyboard.py
│   └── config.py
└── tests/
    ├── test_cli.py
    ├── test_registry.py
    └── test_renderer.py
```

各ファイルの役割:

| ファイル | 役割 |
|---|---|
| `cli.py` | コマンドライン引数の解析 |
| `player.py` | 動画の読み込みと再生制御 |
| `renderer.py` | ASCII・ANSIカラー変換 |
| `registry.py` | 動画登録情報の保存と取得 |
| `audio.py` | 音声再生プロセスの制御 |
| `keyboard.py` | 再生中のキー入力処理 |
| `config.py` | 設定ファイルの場所や共通設定 |
| `test_cli.py` | CLIコマンドのテスト |
| `test_registry.py` | 登録・削除処理のテスト |
| `test_renderer.py` | フレーム変換処理のテスト |

## 9. 使用技術

### 9.1 開発言語

- Python 3.10以上

### 9.2 使用予定ライブラリ

| 技術 | 用途 |
|---|---|
| OpenCV | 動画の読み込みとフレーム処理 |
| argparse | CLIコマンドの解析 |
| pathlib | ファイルパスの処理 |
| subprocess | `ffplay`の起動と終了 |
| JSON | 登録情報の保存 |
| ANSIエスケープシーケンス | ターミナル描画 |
| pytest | 自動テスト |

### 9.3 外部ソフトウェア

音声再生にはFFmpegの`ffplay`を利用する。

音声を使用しない場合は、FFmpegなしでも映像を再生できる構成を目指す。

## 10. 動画変換方式

### 10.1 ASCIIモード

各フレームをグレースケールに変換し、画素の明るさに応じて文字を割り当てる。

使用文字の例:

```text
 .,:;irsXA253hMHGS#9B&@
```

暗い画素には密度の低い文字、明るい画素には密度の高い文字を割り当てる。

### 10.2 カラーモード

ANSI True Colorを使って、各文字に前景色と背景色を設定する。

ブロック文字`▀`を使用し、1文字で上下2画素を表現する。

これにより、通常の空白背景方式より縦方向の解像度を高くできる。

### 10.3 アスペクト比

ターミナルの1文字は正方形ではないため、画像をそのまま縮小すると縦長または横長に見える。

文字セルの縦横比を考慮し、変換時に高さを補正する。

### 10.4 フレーム同期

動画のFPSから各フレームの表示予定時刻を計算する。

処理が予定より速い場合は待機し、処理が遅れた場合は必要に応じてフレームをスキップする。

## 11. エラー処理

以下の状況で、利用者に分かりやすいエラーを表示する。

- 指定した動画ファイルが存在しない
- 登録名が存在しない
- 同じ名前がすでに登録されている
- 動画ファイルを読み込めない
- 設定ファイルが壊れている
- 設定ファイルへ書き込めない
- `--audio`指定時に`ffplay`が存在しない
- ターミナルがANSIカラーに対応していない
- 登録後に動画ファイルが移動されている

エラー表示例:

```text
エラー: 「neko」は登録されていません。
登録一覧は `termvid list` で確認できます。
```

## 12. 対応環境

初期対応予定:

- Linux
- macOS
- Windows Terminal

動作確認対象:

- GNOME Terminal
- Konsole
- macOS Terminal
- iTerm2
- Windows Terminal

ANSI True Colorに対応していないターミナルでは、ASCIIモードを使用する。

## 13. 開発フェーズ

### フェーズ1: 基本再生機能

目標:

- 動画ファイルをOpenCVで読み込む
- フレームをASCII文字へ変換する
- ターミナル上で連続表示する
- `q`で再生を終了する
- FPSに合わせて表示速度を調整する

完了条件:

```bash
termvid run ./sample.mp4
```

上記コマンドでASCII動画を再生できること。

### フェーズ2: 登録機能

目標:

- 動画に名前を付けて登録する
- JSONへ設定を保存する
- 登録名で動画を再生する
- 一覧、詳細、削除コマンドを実装する

完了条件:

```bash
termvid add sample ./sample.mp4
termvid sample
termvid list
termvid show sample
termvid remove sample
```

すべてのコマンドが正常に動作すること。

### フェーズ3: カラー表示

目標:

- ANSI True Colorへ対応する
- ブロック文字で上下2画素を表現する
- ターミナルサイズに合わせて自動調整する

完了条件:

```bash
termvid add sample ./sample.mp4 --mode color
termvid sample
```

カラー動画として再生できること。

### フェーズ4: 音声対応

目標:

- `ffplay`で音声を再生する
- 映像終了時に音声プロセスを停止する
- `q`で終了した場合も音声を停止する

完了条件:

```bash
termvid add sample ./sample.mp4 --mode color --audio
termvid sample
```

映像と音声を同時に再生できること。

### フェーズ5: 操作性改善

目標:

- 一時停止と再開
- ミュート切り替え
- 再生速度変更
- 設定編集コマンド
- エラーメッセージの改善
- ヘルプの整備

### フェーズ6: 配布対応

目標:

- `pip`でインストールできるようにする
- PyPI公開を想定したパッケージ構成にする
- Linux、macOS、Windowsで動作確認する
- READMEとインストール手順を整備する

インストール方法:

```bash
python -m pip install termvid
```

## 14. 開発スケジュール案

| 期間 | 作業内容 |
|---|---|
| 1日目 | プロジェクト作成、OpenCVで動画を読み込む |
| 2日目 | ASCII変換とターミナル描画 |
| 3日目 | FPS同期、終了操作、画面サイズ調整 |
| 4日目 | 動画登録、一覧、詳細、削除 |
| 5日目 | 登録名による再生 |
| 6日目 | ANSIカラー表示 |
| 7日目 | 音声再生 |
| 8日目 | エラー処理と自動テスト |
| 9日目 | Windows、macOS、Linuxで動作確認 |
| 10日目 | README作成、パッケージ化 |

## 15. テスト計画

### 15.1 登録機能

- 新しい名前で動画を登録できる
- 相対パスが絶対パスとして保存される
- 存在しない動画は登録できない
- 同じ名前は通常上書きできない
- `--force`指定時は上書きできる
- 空白を含む不正な登録名を拒否する
- 予約済みの名前を拒否する

### 15.2 再生機能

- 登録名から動画を再生できる
- ASCIIモードで表示できる
- カラーモードで表示できる
- ターミナルサイズに合わせて縮小できる
- `q`で正常に終了できる
- 終了後にカーソルと文字色が元に戻る

### 15.3 音声機能

- `--audio`指定時に`ffplay`を起動できる
- 動画終了時に`ffplay`も終了する
- 強制終了時に音声プロセスが残らない
- `ffplay`がない場合に適切なエラーを表示する

### 15.4 登録データ

- JSONを正常に保存・読み込みできる
- 日本語を含むパスを保存できる
- 壊れたJSONに対してエラーを表示する
- 保存中に失敗しても元の設定を可能な限り保護する

## 16. 初期バージョンの完成条件

以下の操作ができる状態をバージョン`0.1.0`の完成条件とする。

```bash
termvid add badapple ./bad-apple.mp4 --mode ascii
termvid badapple
termvid list
termvid show badapple
termvid remove badapple
```

追加条件:

- ASCIIモードで動画を再生できる
- カラーモードで動画を再生できる
- 動画ごとの設定を保存できる
- 登録名だけで再生できる
- `q`で安全に終了できる
- 終了時にターミナルの表示状態を復元できる
- Linux、macOS、Windows Terminalのいずれかで正常に動作する

## 17. 将来追加する機能

- YouTubeなどのURLから直接再生
- GIFアニメーション対応
- Webカメラのリアルタイム表示
- 字幕表示
- 複数動画のプレイリスト
- ループ再生
- ランダム再生
- 動画の専用ライブラリへのコピー
- 256色ターミナル対応
- Unicodeブロック文字モード
- 点字文字による高解像度表示
- 独自カラーパレット
- 設定のエクスポートとインポート
- シェル補完
- 登録名の別名設定

将来的なコマンド例:

```bash
termvid playlist add favorites neko
termvid playlist add favorites badapple
termvid playlist play favorites
```

## 18. 想定される課題

### 18.1 描画性能

ANSIカラーは1フレームあたりの出力量が多く、ターミナルによっては再生が遅くなる可能性がある。

対策:

- フレームをスキップする
- 最大横幅を制限する
- FPSの上限を設定する
- 同じ色が連続する場合はANSIコードを省略する
- 変更された領域だけを描画する

### 18.2 音声同期

映像変換の負荷によって、映像と音声がずれる可能性がある。

対策:

- 実時間を基準にフレーム位置を決定する
- 遅れたフレームをスキップする
- 将来的にFFmpegからタイムスタンプを取得する

### 18.3 OSごとの違い

キーボード入力、ANSI対応、設定ディレクトリがOSによって異なる。

対策:

- OS依存処理を別モジュールに分離する
- Windows Terminalを推奨環境とする
- 各OSで自動テストと手動確認を行う

## 19. 最終的な利用イメージ

初回のみ動画を登録する。

```bash
termvid add badapple ~/Videos/bad-apple.mp4 --mode ascii
termvid add opening ~/Videos/opening.mp4 --mode color --audio
termvid add neko ~/Videos/cat.mp4 --mode color
```

登録内容を確認する。

```bash
termvid list
```

その後は、登録名だけで再生する。

```bash
termvid badapple
```

```bash
termvid opening
```

```bash
termvid neko
```
```