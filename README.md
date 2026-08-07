# FraTerm

動画をターミナル上でASCII文字やANSIカラーとして再生するCLIツールです．

動画に名前を付けて登録しておけば，次回からはファイルパスを打たずに登録名だけで呼び出せます．

```bash
fraterm add badapple ~/Videos/bad-apple.mp4 --mode ascii
fraterm badapple
```

## 特徴

- 3種類の描画モード（`ascii` / `color` / `mono`）を選べます．
- 動画ごとに描画モード・表示幅・FPS上限・文字セットなどを保存できます．
- 元動画のFPSに同期して再生し，処理が遅れた分はフレームを読み飛ばします．
- 再生中に一時停止・先頭へ戻る・速度変更・ミュートを操作できます．
- `q` でも `Ctrl+C` でも，カーソルと画面の状態を必ず元に戻して終了します．

## 動作環境

| 項目 | 内容 |
|---|---|
| Python | 3.10以上 |
| 必須ライブラリ | opencv-python，numpy |
| 音声再生（任意） | FFmpeg の `ffplay` |
| 対応OS | macOS，Linux，Windows Terminal |

`color` と `mono` は24bitカラー（True Color）対応のターミナルが必要です．非対応の場合は `ascii` を使用してください．

## インストール

リポジトリのルートで次を実行します．

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

音声も再生する場合は，別途FFmpegを導入してください．

```bash
brew install ffmpeg        # macOS
sudo apt install ffmpeg    # Ubuntu
```

## 使い方

### 動画を登録する

```bash
fraterm add <登録名> <動画ファイル> [オプション]
```

```bash
fraterm add badapple ~/Videos/bad-apple.mp4 --mode ascii
fraterm add neko ~/Videos/cat.mp4 --mode color --audio --width 100
```

同じ名前で登録し直す場合は `--force` を付けます．

### 再生する

登録名だけで再生できます．

```bash
fraterm badapple
```

明示的に `play` を書く形式も使えます．オプションを付けると，その回だけ設定を上書きできます（登録内容は変わりません）．

```bash
fraterm play badapple --mode color --width 80
```

登録せずにファイルを直接再生することもできます．

```bash
fraterm run ~/Videos/sample.mp4 --mode color
```

### 一覧・詳細・変更・削除

```bash
fraterm list              # 登録一覧
fraterm show badapple     # 登録内容の詳細
fraterm edit badapple --mode color --audio
fraterm remove badapple   # 登録の削除（動画ファイルは消しません）
```

### 再生中の操作

| キー | 操作 |
|---|---|
| `q` | 再生を終了する |
| `Space` | 一時停止・再開する |
| `r` | 先頭から再生し直す |
| `m` | ミュートを切り替える（`--audio` 指定時のみ） |
| `+` | 再生速度を上げる |
| `-` | 再生速度を下げる |

## オプション

| オプション | 内容 |
|---|---|
| `--mode ascii\|color\|mono` | 描画モード（既定は `ascii`） |
| `--audio` / `--no-audio` | 音声を再生する／しない |
| `--width <桁数>` | 最大表示幅．`auto` でターミナル幅に追従します |
| `--fps <数値>` | 描画FPSの上限．`auto` で動画のFPSに従います |
| `--charset <文字列>` | ASCII変換に使う文字．プリセット名も指定できます |
| `--brightness <値>` | 明るさ補正（-1.0〜1.0） |
| `--contrast <値>` | コントラスト補正（0.1〜5.0） |
| `--no-status` | 画面下部のステータス行を隠す（`play` / `run` のみ） |
| `--force` | 同名の登録を上書きする（`add` のみ） |

文字セットのプリセットは次の4種類です．

| 名前 | 文字 |
|---|---|
| `standard` | ` .,:;irsXA253hMHGS#9B&@` |
| `simple` | ` .:-=+*#%@` |
| `blocks` | ` ░▒▓█` |
| `minimal` | ` .*#` |

## 描画方式

- **ascii**: フレームをグレースケール化し，明るさに応じて文字を割り当てます．
- **color**: ハーフブロック文字 `▀` の前景色と背景色で上下2画素を表現し，縦解像度を2倍にします．
- **mono**: `color` と同じ方式を白黒で描画します．

文字セルは正方形ではないため，縦横比を補正してから縮小します．

## 設定ファイル

登録情報はOSごとの設定ディレクトリにJSONで保存されます．

| OS | 保存場所 |
|---|---|
| macOS | `~/Library/Application Support/fraterm/videos.json` |
| Linux | `~/.config/fraterm/videos.json` |
| Windows | `%APPDATA%\fraterm\videos.json` |

環境変数 `FRATERM_HOME` を設定すると，保存先を任意の場所へ変更できます．

保存されるのは動画ファイルの絶対パスだけで，動画自体はコピーされません．登録後にファイルを移動した場合は，再生時にその旨を表示します．

## 開発

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

インストール時にCコンパイラを利用できる場合は，カラー・モノクロ描画の
ANSI文字列生成をC拡張で高速化します．ビルドできない環境では，同じ出力の
Python実装へ自動的にフォールバックします．状態確認と，リポジトリのルートで
実行する開発用ベンチマークは次のとおりです．

```bash
python -c "from fraterm import renderer; print(renderer.HAS_NATIVE_RENDERER)"
python -m benchmarks.benchmark_renderer
```

| ファイル | 役割 |
|---|---|
| `fraterm/cli.py` | コマンドライン引数の解析 |
| `fraterm/player.py` | 動画の読み込みと再生制御 |
| `fraterm/renderer.py` | ASCII・ANSIカラーへの変換 |
| `fraterm/registry.py` | 登録情報の保存と取得 |
| `fraterm/audio.py` | 音声再生プロセスの制御 |
| `fraterm/keyboard.py` | 再生中のキー入力処理 |
| `fraterm/config.py` | 設定ファイルの場所と共通定数 |
| `fraterm/textwidth.py` | 全角文字を考慮した表示幅の計算 |
| `fraterm/errors.py` | 利用者向けエラーの定義 |

## 既知の制限

- 音声は `ffplay` の別プロセスで再生するため，一時停止や速度変更のたびに再生位置から開始し直します．
- `--fps` は上限の指定です．動画のFPSの約数に丸められるため，指定値ちょうどにはなりません．
- 音声付き再生とWindowsでの動作は，本環境で自動テストを実施していません．

## ライセンス

MIT License．詳細は [LICENSE](LICENSE) を参照してください．
