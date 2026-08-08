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
- `q` でも `Esc` でも `Ctrl+C` でも，カーソルと画面の状態を必ず元に戻して終了します．

## 動作環境

| 項目 | 内容 |
|---|---|
| Python | 3.10以上 |
| 必須ライブラリ | opencv-python，numpy |
| URL再生（任意） | yt-dlp，yt-dlp-ejs，Deno または Node.js 22以上 |
| 音声再生（任意） | FFmpeg の `ffplay` |
| 対応OS | macOS，Linux，Windows Terminal |

`color` と `mono` は24bitカラー（True Color）対応のターミナルが必要です．非対応の場合は `ascii` を使用してください．

## インストール

`git clone` したあと，セットアップスクリプトを実行するだけで準備が整います．

```bash
git clone https://github.com/HR0101/FraTerm.git
cd FraTerm
./setup.sh --all
```

仮想環境の作成，依存ライブラリの導入，外部ツールの確認，動作確認までを一度に行います．

| オプション | 内容 |
|---|---|
| （なし） | Python の依存関係（opencv-python，numpy，yt-dlp）のみ導入します |
| `--with-tools` | ffmpeg と Deno も導入します（Homebrew / apt / dnf を使用） |
| `--dev` | テスト用のライブラリ（pytest など）も導入します |
| `--link` | `fraterm` と `ft` を `~/.local/bin` へ登録し，どこからでも使えるようにします |
| `--all` | 上の3つをまとめて指定します |

何度実行しても問題ありません（既存の仮想環境はそのまま使います）．最後に動作環境の確認結果が表示されます．

```text
==> 準備ができました
    ✓ Python: 3.12.6
    ✓ OpenCV: 5.0.0
    ✓ yt-dlp: モジュールとして利用可能
    ✓ JavaScript: node v22.9.0
    ✓ ffplay: ffplay version 8.1.2
    ✓ C拡張: 有効（描画が高速です）
```

### 手動で導入する場合

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[youtube]"
```

YouTubeは再生用URLの取得にJavaScriptの実行を必要とします．**Deno または Node.js 22以上**のどちらかを導入してください（未導入だと「Signature solving failed」となり，映像の形式を取得できません）．

```bash
brew install deno    # どちらか一方で構いません
brew install node
```

FraTermは導入済みのランタイムを自動的に検出して有効化します（yt-dlp は既定では Deno しか使わないため，Node.jsなどを明示的に有効化します）．

音声も再生する場合は，別途FFmpegを導入してください．

```bash
brew install ffmpeg        # macOS
sudo apt install ffmpeg    # Ubuntu
```

## コマンド一覧

| コマンド | 別名 | 引数 | 内容 |
|---|---|---|---|
| `fraterm run` | — | `<ファイル/URL>` | 登録せずに再生する |
| `fraterm play` | — | `<登録名>` | 登録した動画を再生する |
| `fraterm <登録名>` | — | — | `play` の省略形 |
| `fraterm add` | — | `<登録名> <ファイル/URL>` | 名前を付けて登録する |
| `fraterm list` | `ls` | — | 登録一覧を表示する |
| `fraterm show` | `info` | `<登録名>` | 登録内容の詳細を表示する |
| `fraterm edit` | — | `<登録名>` | 登録内容を変更する（オプション無しで編集画面が開きます） |
| `fraterm remove` | `rm` `delete` | `<登録名>` | 登録を削除する（動画ファイルは消しません） |
| `fraterm cache` | — | — | ダウンロード済み動画の一覧と削除 |
| `fraterm export` | — | `<ファイル>` | 設定と登録動画をバックアップする |
| `fraterm import` | — | `<ファイル>` | バックアップから設定と登録動画を復元する |
| `fraterm defaults` | `config` | — | 毎回のオプションの既定値を設定する |
| `fraterm menu` | `help` | — | 使い方と設定を全画面で表示する |
| `fraterm --version` | — | — | バージョンを表示する |
| `fraterm --help` | — | — | ヘルプを表示する（`fraterm <コマンド> --help` も使えます） |

引数なしで `fraterm` を実行すると，最初の一歩の案内とヘルプが表示されます．すべて `ft` でも実行できます．

### コマンドごとに使えるオプション

| コマンド | 再生・表示のオプション | 専用のオプション |
|---|---|---|
| `run` / `play` | すべて使えます | `--no-status` |
| `add` | すべて使えます | `--force` |
| `edit` | すべて使えます | — |
| `defaults` | すべて使えます | `--clear` |
| `cache` | — | `--clear` |
| `export` | — | `--force` |
| `import` | — | `--force` / `--replace` |
| `list` / `show` / `remove` / `menu` | — | — |

「再生・表示のオプション」の内容は，後述の[オプション](#オプション)を参照してください．

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

### 設定をバックアップ・移行する

既定値と登録動画を1つのJSONへ保存できます．JSONには動画ファイルのパスやURL，
Cookieファイルのパスが含まれますが，Cookieそのものは保存されません．

```bash
fraterm export fraterm-backup.json
fraterm import fraterm-backup.json
fraterm import fraterm-backup.json --replace  # 現在の設定をすべて置き換える
```

既存の登録名がある場合，通常の復元は停止します．上書きする場合は `--force` を指定してください．
バックアップファイルは認証情報を含む可能性があるため，安全な場所で管理してください．

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

`edit` はオプションを付けずに実行すると，**項目を選んで直せる編集画面**が開きます．オプション名を覚えていなくても設定を変更できます．

```bash
fraterm edit badapple
```

```text
「badapple」の設定  変更はすぐ保存されます
────────────────────────────────────────────────────
ファイル: /Users/me/Videos/bad-apple.mp4
← → で1段階ずつ変更，Enter で入力，d で既定へ戻します．

▸ 描画モード        edge          輪郭を | / - \ の記号で描く白黒の線画になります
  文字セット        detailed      70階調．最も密で細かく，情報量が増えます
────────────────────────────────────────────────────
[↑↓]移動 [←→]変更 [Enter]入力 [d]既定へ [q/Esc]終了
```

変更はその場で保存されます．URLを登録した場合は，画質やCookieの項目も表示されます．

登録名やコマンド名を打ち間違えたときは，似た候補を提案します．

```text
$ fraterm myvide
エラー: 「myvide」は登録されていません．
もしかして: 「myvideo」
登録一覧は `fraterm list` で確認できます．
```

### 再生中の操作

| キー | 操作 |
|---|---|
| `q` / `Esc` | 再生を終了する |
| `Space` | 一時停止・再開する |
| `r` | 先頭から再生し直す |
| `←` / `→` または `h` / `l` | 10秒前後へ移動する |
| `m` | ミュートを切り替える（`--audio` 指定時のみ） |
| `+` | 再生速度を上げる |
| `-` | 再生速度を下げる |
| `0` | 音量を上げる |
| `9` | 音量を下げる |
| `s` | 再生中の動画を手元へ保存して登録する |

### 再生中に保存する

`s` を押すと画面下部に入力欄が出ます．登録名を入力して `Enter` を押すと保存され，以降は `fraterm <登録名>` で呼び出せます（`Esc` で取り消せます）．

```text
保存名: myclip_  [Enter]決定 [Esc]取消（英数字・_-.が使えます）
```

- **URLを再生中の場合**: 動画をダウンロードして登録します．以降は**ネットに接続していなくても再生できます**．
- **ローカルファイルを再生中の場合**: ファイルはコピーせず，そのパスと現在の表示設定を登録します．

保存中は再生が一時停止し，完了するとメッセージが出ます．そのときの描画モード・文字セット・音量などもまとめて登録されるので，次回は同じ見た目で再生されます．

## 設定画面

`menu` を実行すると，使い方と設定を1画面で確認できます．`help` でも開けます．

```bash
fraterm menu
```

```text
FraTerm 0.1.0  使い方と設定
 使い方  キー操作 [ 既定の設定 ] 登録一覧  環境  表示言語
────────────────────────────────────────────────────────
▸ 描画モード         edge          文字・線画・カラーの切り替え
  文字セット         standard      濃淡に使う文字
  文字の着色         未設定        文字自体に色を付ける
────────────────────────────────────────────────────────
[Tab]タブ切替 [j/k]移動 [Enter]変更 [q]終了
```

| タブ | 内容 |
|---|---|
| 使い方 | コマンドの一覧と例，短縮形 |
| キー操作 | 再生中とメニューのキー |
| 既定の設定 | 毎回のオプションの既定値．**その場で変更できます** |
| 登録一覧 | 登録済みの動画 |
| 環境 | OpenCV・yt-dlp・ffplay・JavaScriptランタイム・C拡張・24bitカラー対応と，各ファイルの保存先 |
| 表示言語 | 現在の表示言語（日本語のみ対応） |

| キー | 操作 |
|---|---|
| `Tab` | 次のタブへ |
| `↑` `↓`（`k` `j`） | 項目の移動・画面のスクロール |
| `←` `→`（`h` `l`） | タブを切り替える（既定の設定タブでは値の増減） |
| `q` / `Esc` | メニューを閉じる |

### 値の変え方

既定の設定タブでは，2つの方法を用意しています．

| キー | 動作 |
|---|---|
| `←` `→` | 値を1段階ずつ増減する．選択肢は前後の値へ切り替わる |
| `Enter` | 選択肢は次の値へ．数値・文字列は入力欄を開き，打ち込んで `Enter` で確定 |
| `d` | その項目を未設定へ戻す |
| `Esc` | 入力中の値を取り消す |

数値の刻み幅と範囲は項目ごとに決まっています．

| 項目 | 刻み | 範囲 |
|---|---|---|
| 最大表示幅 | 5 | 10〜500 |
| FPS上限 | 5 | 1〜120 |
| 明るさ | 0.1 | -1.0〜1.0 |
| コントラスト | 0.1 | 0.1〜5.0 |
| 音量 | 10 | 0〜100 |
| 音声のずれ補正 | 0.1 | -5.0〜5.0 |

未設定の項目を `←` `→` で変え始めると，その項目の標準的な値（最大表示幅なら80）から始まります．範囲の端では止まるので，行き過ぎる心配はありません．

**値を変えると，右側の説明もその値の内容へ変わります．**

```text
▸ 描画モード         edge          輪郭を | / - \ の記号で描く白黒の線画になります
  文字セット         detailed      70階調．最も密で細かく，情報量が増えます
  文字の着色         true          24bitカラーで着色します．最もなめらかです
  最大表示幅         100           100 桁までに抑えて描画します（端末が狭ければそちらに合わせます）
```

画面に収まらない場合は自動でスクロールし，右下に位置（`[4-16/18]`）が出ます．

依存ツールが足りない場合は，環境タブに導入コマンドが表示されます．

## 毎回のオプションを減らす

よく使うオプションは既定値として保存できます．保存した内容は `run` と `add` に自動で適用されます．

```bash
fraterm defaults -m ascii -s detailed -c true -b chrome --pre-render   # 一度だけ設定する
fraterm run "https://youtu.be/XXXXXXXXXXX"                # 以降はこれだけ
```

```bash
fraterm defaults           # 現在の既定値を表示する
fraterm defaults --clear   # 既定値をすべて削除する
```

コマンドで明示した指定が常に優先されます．登録済みの動画には，登録した時点の設定がそのまま使われます（既定値を後から変えても影響しません）．

### 短縮形

| 短縮形 | 通常の書き方 |
|---|---|
| `-m` | `--mode` |
| `-s` | `--charset` |
| `-c` | `--color` |
| `-w` | `--width` |
| `-a` | `--audio` |
| `-q` | `--quality` |
| `-b` | `--cookies-from-browser` |

```bash
# 以前の書き方
fraterm run "<URL>" --mode ascii --charset detailed --color true --audio --cookies-from-browser chrome

# 短縮形を使う場合
fraterm run "<URL>" -m ascii -s detailed -c true -a -b chrome

# 既定値を保存してある場合
fraterm run "<URL>" -a

# 再生前に全フレームを生成してから流す（高FPSでのカクつきを抑える）
fraterm run "<URL>" --fps 60 --pre-render
```

## オプション

| オプション | 内容 |
|---|---|
| `--mode ascii\|edge\|color\|mono` | 描画モード（既定は `ascii`） |
| `--audio` / `--no-audio` | 音声を再生する／しない |
| `--volume <値>` | 音量（0〜100，既定は100） |
| `--audio-offset <秒>` | 音声のずれを補正します（正の値で音声が先行します） |
| `--width <桁数>` | 最大表示幅．`auto` でターミナル幅に追従します |
| `--fps <数値>` | 描画FPSの上限．`auto` で動画のFPSに従います |
| `--pre-render` / `--no-pre-render` | 再生前に全フレームを文字列化する／しない |
| `--charset <文字列>` | 変換に使う文字．プリセット名も指定できます（`edge` では線以外の塗りに使います） |
| `--color off\|256\|true` | 文字自体に色を付けます（`ascii` / `edge` 用．既定は `off`） |
| `--brightness <値>` | 明るさ補正（-1.0〜1.0） |
| `--contrast <値>` | コントラスト補正（0.1〜5.0） |
| `--quality <値>` | URL再生時の画質（`360` / `480` / `720` / `1080` / `best` / `worst`） |
| `--cache` / `--no-cache` | URLをダウンロードしてから再生する／直接再生する |
| `--cookies-from-browser <ブラウザ>` | ログイン済みブラウザのCookieを使う |
| `--cookies <ファイル>` | 書き出したCookieファイルを使う |
| `--player-client <名前>` | YouTubeの取得方法を切り替える（上級者向け） |
| `--no-status` | 画面下部のステータス行を隠す（`play` / `run` のみ） |
| `--force` | 同名の登録を上書きする（`add` のみ） |

文字セットのプリセットは次の5種類です．

| 名前 | 文字数 | 用途 |
|---|---|---|
| `standard` | 23 | 既定．濃淡のバランスが良い |
| `detailed` | 70 | 階調が最も細かく，密度が高い |
| `simple` | 10 | すっきりした見た目 |
| `blocks` | 5 | ` ░▒▓█` によるブロック表現 |
| `minimal` | 4 | ` .*#` のみの軽い表現 |

### 文字に色を付ける

`--color` を使うと，ブロック文字ではなく**文字そのもの**に色が付きます．ASCIIアートの形を保ったままカラーにしたい場合はこちらを使います．

```bash
fraterm run video.mp4 --mode ascii --charset detailed --color 256   # 256色
fraterm run video.mp4 --mode ascii --charset detailed --color true  # 24bitカラー
fraterm run video.mp4 --mode edge --color 256                       # 線画に着色
```

`--mode color` はハーフブロック文字を敷き詰める方式なので，見た目はモザイク調になります．文字で形を表現したい場合は `--mode ascii` に `--color` を組み合わせてください．

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
| `fraterm/menu.py` | 使い方と設定の全画面メニュー |
| `fraterm/settings.py` | オプションの既定値の保存 |
| `fraterm/backup.py` | 設定と登録動画のバックアップ・復元 |
| `fraterm/diagnostics.py` | 依存ツールと保存先の診断 |
| `fraterm/terminal.py` | 端末制御のエスケープシーケンス |
| `fraterm/textwidth.py` | 全角文字を考慮した表示幅の計算 |
| `fraterm/errors.py` | 利用者向けエラーの定義 |

## 既知の制限

- 音声は `ffplay` の別プロセスで再生するため，一時停止・速度変更・音量変更のたびに現在位置から再生し直します．`ffplay` の起動には0.25〜0.55秒ほどかかるので，映像が先行しないよう上限の0.55秒を見込んで先の位置から鳴らします．ずれを感じる場合は `--audio-offset` で微調整してください（正の値で音声が先行します）．
- `--fps` は上限の指定です．動画のFPSの約数に丸められるため，指定値ちょうどにはなりません．
- `--pre-render` は再生開始前に動画全体を変換するため，長い動画では開始まで時間がかかります．変換結果は一時ファイルに保存し，再生中のメモリ使用量を抑えます．再生中に端末サイズを変えた場合は，現在位置から通常描画へ切り替えて新しいサイズへ追従します．
- URL再生では，映像と音声が1つにまとまった形式のみを選びます．YouTubeの場合は360p前後が上限になることが多く，`--quality 720` を指定しても自動的に下位の形式へ切り替わります（端末表示では実用上ほとんど差がありません）．
- ダウンロードの進捗は表示されません．長い動画に `--cache` を指定した場合は，完了までしばらく待つ必要があります．
- URLの解決には数秒〜1分程度かかります．特に `--cookies-from-browser` はブラウザのCookieを毎回すべて読み出すため時間がかかります．繰り返し見る動画は `--cache` で保存すると2回目以降は待ち時間がなくなります．
- サイト側の仕様変更で取得に失敗する場合は，`yt-dlp -U` で更新してください．
- Windowsでの動作は，本環境で自動テストを実施していません．

## ライセンス

MIT License．詳細は [LICENSE](LICENSE) を参照してください．
