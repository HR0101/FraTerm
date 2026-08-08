# FraTerm

動画をターミナル上でASCII文字やANSIカラーとして再生するCLIツールです．

動画に名前を付けて登録しておけば，次回からはファイルパスを打たずに登録名だけで呼び出せます．

```bash
fraterm add badapple ~/Videos/bad-apple.mp4 --mode ascii
fraterm badapple
```

`fraterm` は `ft` という短い名前でも実行できます．ヘルプやエラーの案内も，実際に打った名前に合わせて表示されます．

```bash
ft badapple
```

## 特徴

- 4種類の描画モード（`ascii` / `edge` / `color` / `mono`）を選べます．
- 輪郭を検出して `|` `/` `-` `\` の記号で線を描く，白黒の線画モードがあります．
- YouTubeなどのURLをそのまま再生・登録できます（`yt-dlp` が必要です）．
- 動画ごとに描画モード・表示幅・FPS上限・文字セットなどを保存できます．
- 元動画のFPSに同期して再生し，処理が遅れた分はフレームを読み飛ばします．
- 再生中に一時停止・先頭へ戻る・速度変更・ミュートを操作できます．
- `q` でも `Ctrl+C` でも，カーソルと画面の状態を必ず元に戻して終了します．

## 動作環境

| 項目 | 内容 |
|---|---|
| Python | 3.10以上 |
| 必須ライブラリ | opencv-python，numpy |
| URL再生（任意） | yt-dlp |
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

URLからの再生を使う場合は，`yt-dlp` も導入します．

```bash
python -m pip install -e ".[youtube]"
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

### URLから再生する

YouTubeなどのURLを，動画ファイルと同じように扱えます．`yt-dlp` が対応しているサイトであれば再生できます．

```bash
fraterm run "https://www.youtube.com/watch?v=XXXXXXXXXXX" --mode color
fraterm add zoo "https://www.youtube.com/watch?v=XXXXXXXXXXX" --quality 480 --mode ascii
fraterm zoo
```

URLは引用符で囲んでください．`?` や `&` を含むURLをそのまま書くと，zshでは `zsh: no matches found:` というエラーになります（コマンドが起動する前にシェルが止めるためです）．

既定では，ダウンロードせずに直接ストリーミング再生します．`--cache` を付けると，動画をダウンロードしてから再生します．

```bash
fraterm add zoo https://www.youtube.com/watch?v=XXXXXXXXXXX --cache
```

`--cache` で登録した動画は，2回目以降**ネットワークに接続せず**キャッシュから再生されます．キャッシュを削除した場合は自動で取得し直します．

```bash
fraterm cache           # キャッシュの一覧と合計サイズ
fraterm cache --clear   # キャッシュをすべて削除
```

なお直接リンクは数時間で失効するため，登録内容には元のURLを保存し，再生のたびに解決し直します．動画の視聴にあたっては，各サイトの利用規約と著作権を尊重してご利用ください．

### ログインが必要な動画

年齢制限やメンバー限定の動画は，ログイン済みブラウザのCookieを渡すことで，ご自身のアカウントとして視聴できます．

```bash
fraterm run <URL> --cookies-from-browser chrome
fraterm add name <URL> --cookies-from-browser safari    # 登録すれば次回以降は不要です
```

指定できるブラウザは `brave` `chrome` `chromium` `edge` `firefox` `opera` `safari` `vivaldi` `whale` です．`chrome:Profile 1` のようにプロファイルも指定できます．ブラウザの拡張機能で書き出したファイルを使う場合は `--cookies <ファイル>` を指定します．

毎回指定する代わりに，環境変数でも設定できます．

```bash
export FRATERM_COOKIES_FROM_BROWSER=chrome
```

macOSでは次の点に注意してください．

- **Chrome系**: Cookieの復号でキーチェーンへのアクセス許可を求められることがあります．初回のみ許可してください．
- **Safari**: ターミナルに「フルディスクアクセス」の許可が必要です（システム設定 → プライバシーとセキュリティ）．
- ブラウザ起動中はCookieファイルがロックされ，読み出しに失敗する場合があります．その際はブラウザを終了してから実行してください．

YouTubeはブラウザの利用中にCookieを頻繁に更新するため，通常のウィンドウから取り出したCookieはすぐ無効になることがあります．うまくいかない場合は，シークレットウィンドウでログインし，**そのウィンドウを閉じずに**別ウィンドウを閉じてから実行する方法が確実です（yt-dlpの推奨手順）．

それでも取得できない場合は，`--player-client` で取得方法を切り替えられます．

```bash
fraterm run <URL> --cookies-from-browser chrome --player-client mweb
```

ただし単独のクライアントを強制すると，かえって取得できなくなることがあります．基本は指定せず，エラーの案内に従って必要なときだけ使ってください．

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
| `--mode ascii\|edge\|color\|mono` | 描画モード（既定は `ascii`） |
| `--audio` / `--no-audio` | 音声を再生する／しない |
| `--width <桁数>` | 最大表示幅．`auto` でターミナル幅に追従します |
| `--fps <数値>` | 描画FPSの上限．`auto` で動画のFPSに従います |
| `--charset <文字列>` | 変換に使う文字．プリセット名も指定できます（`edge` では線以外の塗りに使います） |
| `--brightness <値>` | 明るさ補正（-1.0〜1.0） |
| `--contrast <値>` | コントラスト補正（0.1〜5.0） |
| `--quality <値>` | URL再生時の画質（`360` / `480` / `720` / `1080` / `best` / `worst`） |
| `--cache` / `--no-cache` | URLをダウンロードしてから再生する／直接再生する |
| `--cookies-from-browser <ブラウザ>` | ログイン済みブラウザのCookieを使う |
| `--cookies <ファイル>` | 書き出したCookieファイルを使う |
| `--player-client <名前>` | YouTubeの取得方法を切り替える（上級者向け） |
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

| モード | 方式 | 見え方 |
|---|---|---|
| `ascii` | 明るさに応じて文字を割り当てる | 文字の濃淡で階調を表現します |
| `edge` | 輪郭を検出し，線の向きを記号で描く | 物の形が線として現れる白黒の線画になります |
| `color` | ハーフブロック文字 `▀` の前景色と背景色で上下2画素を表現する | 縦解像度が2倍のカラー映像になります |
| `mono` | `color` と同じ方式を白黒で描く | 白黒の映像になります |

文字セルは正方形ではないため，縦横比を補正してから縮小します．

### edgeモードの調整

輝度の勾配をSobelフィルタで求め，勾配と直交する向きに応じて `|` `/` `-` `\` を割り当てます．線と判定するしきい値はフレームごとに自動調整されるため，明るい映像でも暗い映像でも線の量がほぼ一定になります．

線以外の部分は `--charset` で指定した文字で塗ります．既定は薄い ` .:` です．

```bash
fraterm run video.mp4 --mode edge                    # 既定（線＋薄い塗り）
fraterm run video.mp4 --mode edge --charset "  "     # 線だけの純粋な線画
fraterm run video.mp4 --mode edge --charset " .:*#"  # 階調を強めに残す
fraterm run video.mp4 --mode edge --contrast 1.6     # 線を出やすくする
```

## 設定ファイル

登録情報はOSごとの設定ディレクトリにJSONで保存されます．

| OS | 保存場所 |
|---|---|
| macOS | `~/Library/Application Support/fraterm/videos.json` |
| Linux | `~/.config/fraterm/videos.json` |
| Windows | `%APPDATA%\fraterm\videos.json` |

環境変数 `FRATERM_HOME` を設定すると，保存先を任意の場所へ変更できます．`--cache` でダウンロードした動画は，同じディレクトリの `cache/` に保存されます．

保存されるのは動画ファイルの絶対パス（またはURL）だけで，動画自体はコピーされません．登録後にファイルを移動した場合は，再生時にその旨を表示します．

## 開発

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

インストール時にCコンパイラを利用できる場合は，ASCII変換とカラー・モノクロの
ANSI文字列生成をC拡張で高速化します．フレーム縮小には，リアルタイム表示での
速度と画質のバランスが良い線形補間を使用します．C拡張をビルドできない環境では，
同じ出力のPython実装へ自動的にフォールバックします．状態確認と，リポジトリの
ルートで実行する開発用ベンチマークは次のとおりです．

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
| `fraterm/source.py` | URLの解決とダウンロードしたファイルの管理 |
| `fraterm/audio.py` | 音声再生プロセスの制御 |
| `fraterm/keyboard.py` | 再生中のキー入力処理 |
| `fraterm/config.py` | 設定ファイルの場所と共通定数 |
| `fraterm/textwidth.py` | 全角文字を考慮した表示幅の計算 |
| `fraterm/errors.py` | 利用者向けエラーの定義 |

## 既知の制限

- 音声は `ffplay` の別プロセスで再生するため，一時停止や速度変更のたびに再生位置から開始し直します．
- `--fps` は上限の指定です．動画のFPSの約数に丸められるため，指定値ちょうどにはなりません．
- URL再生では，映像と音声が1つにまとまった形式のみを選びます．YouTubeの場合は360p前後が上限になることが多く，`--quality 720` を指定しても自動的に下位の形式へ切り替わります（端末表示では実用上ほとんど差がありません）．
- ダウンロードの進捗は表示されません．長い動画に `--cache` を指定した場合は，完了までしばらく待つ必要があります．
- サイト側の仕様変更で取得に失敗する場合は，`yt-dlp -U` で更新してください．
- 音声付き再生とWindowsでの動作は，本環境で自動テストを実施していません．

## ライセンス

MIT License．詳細は [LICENSE](LICENSE) を参照してください．
