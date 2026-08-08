"""コマンドライン引数を解析し，各機能を呼び出すモジュール."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Sequence

from . import config, source
from .errors import FraTermError, VideoFileError
from .registry import Registry, VideoEntry, resolveVideoPath
from .textwidth import displayWidth, padToWidth

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INTERRUPTED = 130


class _Unset:
  """引数が指定されなかったことを表す番兵クラス."""

  def __repr__(self) -> str:  # デバッグ表示用
    return "UNSET"

  def __bool__(self) -> bool:
    return False


UNSET = _Unset()

# 「自動・既定に戻す」を意味する入力値
AUTO_KEYWORDS = frozenset({"auto", "none", "default", "-"})

# 登録名として解釈せず，サブコマンドとして扱う語
KNOWN_COMMANDS = frozenset(
  {
    "add",
    "remove",
    "rm",
    "delete",
    "list",
    "ls",
    "show",
    "info",
    "edit",
    "play",
    "run",
    "cache",
  }
)

# 再生時に上書きできる描画・再生の設定
PLAYBACK_ATTRIBUTES = (
  "mode",
  "audio",
  "width",
  "fps",
  "charset",
  "brightness",
  "contrast",
  "showStatus",
)

# URLを解決する際に使用する設定
SOURCE_ATTRIBUTES = (
  "quality",
  "cache",
  "cookiesFromBrowser",
  "cookiesFile",
  "playerClient",
)

# 登録情報として保存する設定（ステータス行の表示は保存しない）
STORED_ATTRIBUTES = tuple(
  attribute for attribute in PLAYBACK_ATTRIBUTES if attribute != "showStatus"
) + SOURCE_ATTRIBUTES

# キャッシュ容量の表示に使う単位
BYTE_UNITS = ("B", "KB", "MB", "GB", "TB")
BYTES_PER_UNIT = 1024.0

# 明るさの指定範囲
MIN_BRIGHTNESS = -1.0
MAX_BRIGHTNESS = 1.0

# コントラストの指定範囲
MIN_CONTRAST = 0.1
MAX_CONTRAST = 5.0

def buildEpilog() -> str:
  """ヘルプの末尾に表示する使用例を組み立てる（実際のコマンド名に合わせる）."""
  name = config.commandName()
  return f"""使用例:
  {name} add badapple ~/Videos/bad-apple.mp4 --mode ascii
  {name} badapple
  {name} list
  {name} show badapple
  {name} edit badapple --mode color --audio
  {name} remove badapple
  {name} run ~/Videos/sample.mp4 --mode color

URLから再生する（yt-dlp が必要です）:
  {name} run "https://www.youtube.com/watch?v=XXXXXXXXXXX" --mode color
  {name} add opening "https://www.youtube.com/watch?v=XXXXXXXXXXX" --quality 480
  {name} run "<URL>" --cookies-from-browser chrome   # 年齢制限などの動画
  {name} cache --clear

再生中の操作:
  q: 終了 / space: 一時停止・再開 / r: 先頭から / m: ミュート / +,-: 再生速度

URLは引用符で囲んでください（zshでは `?` がエラーになります）．
"""


# ---------------------------------------------------------------------------
# 引数の型変換
# ---------------------------------------------------------------------------


def optionalPositiveInt(rawValue: str) -> int | None:
  """正の整数，または自動を意味する None へ変換する."""
  if rawValue.lower() in AUTO_KEYWORDS:
    return None
  try:
    number = int(rawValue)
  except ValueError as error:
    raise argparse.ArgumentTypeError(
      f"整数または auto を指定してください: {rawValue}"
    ) from error
  if number <= 0:
    raise argparse.ArgumentTypeError("1以上の整数を指定してください．")
  return number


def optionalPositiveFloat(rawValue: str) -> float | None:
  """正の実数，または自動を意味する None へ変換する."""
  if rawValue.lower() in AUTO_KEYWORDS:
    return None
  try:
    number = float(rawValue)
  except ValueError as error:
    raise argparse.ArgumentTypeError(
      f"数値または auto を指定してください: {rawValue}"
    ) from error
  if number <= 0:
    raise argparse.ArgumentTypeError("0より大きい数値を指定してください．")
  return number


def brightnessValue(rawValue: str) -> float:
  """明るさ補正値へ変換する."""
  try:
    number = float(rawValue)
  except ValueError as error:
    raise argparse.ArgumentTypeError(f"数値を指定してください: {rawValue}") from error
  if not MIN_BRIGHTNESS <= number <= MAX_BRIGHTNESS:
    raise argparse.ArgumentTypeError(
      f"{MIN_BRIGHTNESS}〜{MAX_BRIGHTNESS} の範囲で指定してください．"
    )
  return number


def contrastValue(rawValue: str) -> float:
  """コントラスト補正値へ変換する."""
  try:
    number = float(rawValue)
  except ValueError as error:
    raise argparse.ArgumentTypeError(f"数値を指定してください: {rawValue}") from error
  if not MIN_CONTRAST <= number <= MAX_CONTRAST:
    raise argparse.ArgumentTypeError(
      f"{MIN_CONTRAST}〜{MAX_CONTRAST} の範囲で指定してください．"
    )
  return number


def optionalText(rawValue: str) -> str | None:
  """文字列，または既定へ戻すことを意味する None へ変換する."""
  if rawValue.lower() in AUTO_KEYWORDS:
    return None
  return rawValue


def cookieBrowserValue(rawValue: str) -> str | None:
  """Cookieを読み出すブラウザの指定を検証する.

  yt-dlp と同じく `chrome:Profile 1` のようなプロファイル指定も受け付ける.
  """
  if rawValue.lower() in AUTO_KEYWORDS:
    return None

  browserName = rawValue.split(":", 1)[0].strip().lower()
  if browserName not in config.SUPPORTED_COOKIE_BROWSERS:
    raise argparse.ArgumentTypeError(
      f"対応していないブラウザです: {rawValue}"
      f"（指定できる値: {'，'.join(config.SUPPORTED_COOKIE_BROWSERS)}）"
    )
  return rawValue


def charsetValue(rawValue: str) -> str | None:
  """文字セットの指定（プリセット名または文字列）へ変換する."""
  if rawValue.lower() in AUTO_KEYWORDS:
    return None
  if rawValue in config.CHARSET_PRESETS:
    return rawValue
  if len(rawValue) < 2:
    raise argparse.ArgumentTypeError(
      "文字セットは2文字以上必要です（暗い順に並べてください）．"
    )
  return rawValue


# ---------------------------------------------------------------------------
# パーサの組み立て
# ---------------------------------------------------------------------------


def addPlaybackArguments(parser: argparse.ArgumentParser, includeStatus: bool) -> None:
  """再生設定に関する共通オプションを追加する."""
  presetNames = "，".join(config.CHARSET_PRESETS)

  parser.add_argument(
    "--mode",
    choices=config.AVAILABLE_MODES,
    default=UNSET,
    help=f"描画モード（既定: {config.DEFAULT_MODE}）",
  )
  parser.add_argument(
    "--audio",
    dest="audio",
    action="store_const",
    const=True,
    default=UNSET,
    help="音声を再生する（ffplay が必要）",
  )
  parser.add_argument(
    "--no-audio",
    dest="audio",
    action="store_const",
    const=False,
    help="音声を再生しない",
  )
  parser.add_argument(
    "--width",
    type=optionalPositiveInt,
    default=UNSET,
    metavar="桁数",
    help="最大表示幅（auto でターミナル幅に追従）",
  )
  parser.add_argument(
    "--fps",
    type=optionalPositiveFloat,
    default=UNSET,
    metavar="FPS",
    help="描画FPSの上限（auto で動画のFPSに従う）",
  )
  parser.add_argument(
    "--charset",
    type=charsetValue,
    default=UNSET,
    metavar="文字列",
    help=f"ASCII変換に使う文字（プリセット: {presetNames}）",
  )
  parser.add_argument(
    "--brightness",
    type=brightnessValue,
    default=UNSET,
    metavar="値",
    help=f"明るさ補正（{MIN_BRIGHTNESS}〜{MAX_BRIGHTNESS}，既定: {config.DEFAULT_BRIGHTNESS}）",
  )
  parser.add_argument(
    "--contrast",
    type=contrastValue,
    default=UNSET,
    metavar="値",
    help=f"コントラスト補正（{MIN_CONTRAST}〜{MAX_CONTRAST}，既定: {config.DEFAULT_CONTRAST}）",
  )

  parser.add_argument(
    "--quality",
    choices=config.QUALITY_CHOICES,
    default=UNSET,
    help=f"URL再生時の画質（既定: {config.DEFAULT_QUALITY}）",
  )
  parser.add_argument(
    "--cache",
    dest="cache",
    action="store_const",
    const=True,
    default=UNSET,
    help="URL再生時に，ダウンロードしてから再生する",
  )
  parser.add_argument(
    "--no-cache",
    dest="cache",
    action="store_const",
    const=False,
    help="URL再生時に，ダウンロードせず直接再生する",
  )
  parser.add_argument(
    "--cookies-from-browser",
    dest="cookiesFromBrowser",
    type=cookieBrowserValue,
    default=UNSET,
    metavar="ブラウザ",
    help=(
      "ログイン済みブラウザのCookieを使う"
      f"（{'，'.join(config.SUPPORTED_COOKIE_BROWSERS)}）"
    ),
  )
  parser.add_argument(
    "--cookies",
    dest="cookiesFile",
    type=optionalText,
    default=UNSET,
    metavar="ファイル",
    help="書き出したCookieファイルを使う",
  )
  parser.add_argument(
    "--player-client",
    dest="playerClient",
    type=optionalText,
    default=UNSET,
    metavar="名前",
    help=(
      "YouTubeの取得方法を切り替える"
      f"（例: {'，'.join(config.COMMON_PLAYER_CLIENTS)}）"
    ),
  )

  if includeStatus:
    parser.add_argument(
      "--no-status",
      dest="showStatus",
      action="store_const",
      const=False,
      default=UNSET,
      help="画面下部のステータス行を表示しない",
    )


def buildParser() -> argparse.ArgumentParser:
  """サブコマンドを含むパーサを構築する."""
  parser = argparse.ArgumentParser(
    prog=config.commandName(),
    description="動画をターミナル上でASCII・ANSIカラーとして再生するCLIツールです．",
    epilog=buildEpilog(),
    formatter_class=argparse.RawDescriptionHelpFormatter,
  )
  parser.add_argument(
    "--version",
    action="version",
    version=f"{config.commandName()} {config.VERSION}",
    help="バージョンを表示する",
  )

  subparsers = parser.add_subparsers(dest="command", metavar="コマンド")

  # add ---------------------------------------------------------------------
  addParser = subparsers.add_parser(
    "add",
    help="動画に名前を付けて登録する",
    description="動画ファイルまたはURLに名前を付けて登録します．",
  )
  addParser.add_argument("name", help="登録名")
  addParser.add_argument("path", help="動画ファイルのパス，またはURL")
  addPlaybackArguments(addParser, includeStatus=False)
  addParser.add_argument(
    "--force", action="store_true", help="同じ登録名がある場合に上書きする"
  )
  addParser.set_defaults(handler=handleAdd)

  # list --------------------------------------------------------------------
  listParser = subparsers.add_parser(
    "list", aliases=["ls"], help="登録一覧を表示する", description="登録一覧を表示します．"
  )
  listParser.set_defaults(handler=handleList)

  # show --------------------------------------------------------------------
  showParser = subparsers.add_parser(
    "show",
    aliases=["info"],
    help="登録内容の詳細を表示する",
    description="登録内容の詳細を表示します．",
  )
  showParser.add_argument("name", help="登録名")
  showParser.set_defaults(handler=handleShow)

  # edit --------------------------------------------------------------------
  editParser = subparsers.add_parser(
    "edit", help="登録内容を変更する", description="登録済みの設定を変更します．"
  )
  editParser.add_argument("name", help="登録名")
  addPlaybackArguments(editParser, includeStatus=False)
  editParser.set_defaults(handler=handleEdit)

  # remove ------------------------------------------------------------------
  removeParser = subparsers.add_parser(
    "remove",
    aliases=["rm", "delete"],
    help="登録を削除する",
    description="登録を削除します．動画ファイル自体は削除しません．",
  )
  removeParser.add_argument("name", help="登録名")
  removeParser.set_defaults(handler=handleRemove)

  # play --------------------------------------------------------------------
  playParser = subparsers.add_parser(
    "play",
    help="登録した動画を再生する",
    description="登録した動画を再生します．オプションは今回の再生にのみ適用されます．",
  )
  playParser.add_argument("name", help="登録名")
  addPlaybackArguments(playParser, includeStatus=True)
  playParser.set_defaults(handler=handlePlay)

  # run ---------------------------------------------------------------------
  runParser = subparsers.add_parser(
    "run",
    help="動画ファイルやURLを登録せずに再生する",
    description="動画ファイルまたはURLを登録せずに再生します．",
  )
  runParser.add_argument("path", help="動画ファイルのパス，またはURL")
  addPlaybackArguments(runParser, includeStatus=True)
  runParser.set_defaults(handler=handleRun)

  # cache -------------------------------------------------------------------
  cacheParser = subparsers.add_parser(
    "cache",
    help="ダウンロード済み動画を管理する",
    description="URLからダウンロードした動画の一覧表示と削除を行います．",
  )
  cacheParser.add_argument(
    "--clear", action="store_true", help="キャッシュをすべて削除する"
  )
  cacheParser.set_defaults(handler=handleCache)

  return parser


def expandImplicitPlay(rawArgs: Sequence[str]) -> list[str]:
  """`fraterm <登録名>` を `fraterm play <登録名>` として解釈できるようにする."""
  arguments = list(rawArgs)
  if not arguments:
    return arguments

  first = arguments[0]
  if first.startswith("-") or first in KNOWN_COMMANDS:
    return arguments
  return ["play"] + arguments


# ---------------------------------------------------------------------------
# 各コマンドの処理
# ---------------------------------------------------------------------------


def valueOr(value: Any, defaultValue: Any) -> Any:
  """指定されていない引数を既定値へ置き換える."""
  return defaultValue if isinstance(value, _Unset) else value


def collectChanges(args: argparse.Namespace) -> dict[str, Any]:
  """実際に指定された設定だけを辞書として取り出す."""
  changes: dict[str, Any] = {}
  for attribute in STORED_ATTRIBUTES:
    value = getattr(args, attribute, UNSET)
    if not isinstance(value, _Unset):
      changes[attribute] = value
  return changes


def storablePath(rawPath: str) -> str:
  """登録する入力を，URLならそのまま，ファイルなら絶対パスへ変換する."""
  if config.isUrl(rawPath):
    return rawPath.strip()
  return resolveVideoPath(rawPath)


def handleAdd(args: argparse.Namespace) -> int:
  """動画ファイルまたはURLを登録する."""
  entry = VideoEntry(
    name=args.name,
    path=storablePath(args.path),
    mode=valueOr(args.mode, config.DEFAULT_MODE),
    audio=valueOr(args.audio, False),
    width=valueOr(args.width, None),
    fps=valueOr(args.fps, None),
    charset=valueOr(args.charset, None),
    brightness=valueOr(args.brightness, config.DEFAULT_BRIGHTNESS),
    contrast=valueOr(args.contrast, config.DEFAULT_CONTRAST),
    quality=valueOr(args.quality, None),
    cache=valueOr(args.cache, False),
    cookiesFromBrowser=valueOr(args.cookiesFromBrowser, None),
    cookiesFile=valueOr(args.cookiesFile, None),
    playerClient=valueOr(args.playerClient, None),
  )

  Registry().add(entry, force=args.force)
  print(f"「{entry.name}」を登録しました．")
  if entry.isRemote and not source.isAvailable():
    print("注意: URLの再生には yt-dlp が必要です（python -m pip install yt-dlp）．")
  print(f"再生するには `{config.commandName()} {entry.name}` を実行してください．")
  return EXIT_OK


def handleList(args: argparse.Namespace) -> int:
  """登録一覧を表示する."""
  entries = Registry().load()
  if not entries:
    print("登録されている動画はありません．")
    print(f"`{config.commandName()} add <登録名> <動画ファイル>` で登録できます．")
    return EXIT_OK

  headers = ("NAME", "MODE", "AUDIO", "WIDTH", "FPS", "VIDEO")
  rows = [
    (
      entry.name,
      entry.mode,
      "yes" if entry.audio else "no",
      "auto" if entry.width is None else str(entry.width),
      "auto" if entry.fps is None else f"{entry.fps:g}",
      entry.path,
    )
    for _, entry in sorted(entries.items())
  ]

  widths = [
    max(displayWidth(row[index]) for row in (headers, *rows))
    for index in range(len(headers))
  ]

  print("  ".join(padToWidth(headers[i], widths[i]) for i in range(len(headers))).rstrip())
  for row in rows:
    print("  ".join(padToWidth(row[i], widths[i]) for i in range(len(row))).rstrip())
  return EXIT_OK


def handleShow(args: argparse.Namespace) -> int:
  """登録内容の詳細を表示する."""
  entry = Registry().get(args.name)

  charsetLabel = "既定" if entry.charset is None else entry.charset
  if entry.charset in config.CHARSET_PRESETS:
    charsetLabel = f"{entry.charset}（{config.CHARSET_PRESETS[entry.charset]}）"

  items = [
    ("登録名", entry.name),
    ("URL" if entry.isRemote else "動画ファイル", entry.path),
    ("描画モード", entry.mode),
    ("音声", "再生する" if entry.audio else "再生しない"),
    ("最大表示幅", "auto" if entry.width is None else f"{entry.width} 桁"),
    ("FPS上限", "auto" if entry.fps is None else f"{entry.fps:g}"),
    ("文字セット", charsetLabel),
    ("明るさ", f"{entry.brightness:g}"),
    ("コントラスト", f"{entry.contrast:g}"),
  ]

  if entry.isRemote:
    qualityLabel = entry.quality or f"{config.DEFAULT_QUALITY}（既定）"
    cacheLabel = "ダウンロードして再生" if entry.cache else "直接ストリーミング"
    cachedFile = entry.cachedFile()
    if cachedFile is not None:
      cacheLabel += f"（保存済み: {cachedFile}）"
    items.append(("画質", qualityLabel))
    items.append(("キャッシュ", cacheLabel))

    if entry.cookiesFromBrowser:
      items.append(("Cookie", f"{entry.cookiesFromBrowser} のログイン情報を使用"))
    elif entry.cookiesFile:
      items.append(("Cookie", entry.cookiesFile))

    if entry.playerClient:
      items.append(("取得方法", entry.playerClient))

  labelWidth = max(displayWidth(label) for label, _ in items)
  for label, value in items:
    print(f"{padToWidth(label, labelWidth)} : {value}")

  if not entry.videoExists():
    print("警告: 動画ファイルが見つかりません．移動または削除された可能性があります．")
  return EXIT_OK


def handleEdit(args: argparse.Namespace) -> int:
  """登録内容を変更する."""
  changes = collectChanges(args)
  if not changes:
    raise FraTermError(
      "変更する項目が指定されていません．",
      hint=f"例: {config.commandName()} edit {args.name} --mode color --audio",
    )

  entry = Registry().update(args.name, changes)
  print(f"「{entry.name}」の設定を変更しました．")
  for key, value in changes.items():
    print(f"  {key}: {value}")
  return EXIT_OK


def handleRemove(args: argparse.Namespace) -> int:
  """登録を削除する."""
  entry = Registry().remove(args.name)
  print(f"「{entry.name}」の登録を削除しました．（動画ファイルは削除していません）")
  return EXIT_OK


def handlePlay(args: argparse.Namespace) -> int:
  """登録した動画を再生する."""
  playerModule = importPlayerModule()

  entry = Registry().get(args.name)
  if not entry.videoExists():
    raise VideoFileError(
      f"「{entry.name}」の動画ファイルが見つかりません: {entry.path}",
      hint=(
        f"ファイルを元の場所へ戻すか，`{config.commandName()} add {entry.name} "
        f"<新しいパス> --force` で登録し直してください．"
      ),
    )

  playable = resolvePlaybackSource(entry, args)

  options = playerModule.PlaybackOptions.fromEntry(entry)
  options.duration = playable.duration
  applyOverrides(options, args)
  return startPlayback(playerModule, playable.path, options)


def handleRun(args: argparse.Namespace) -> int:
  """登録せずに動画ファイルやURLを再生する."""
  playerModule = importPlayerModule()

  quality, useCache, cookies = sourceSettings(args)
  playable = source.openSource(args.path, quality, useCache, notifyProgress, cookies)

  options = playerModule.PlaybackOptions(
    title=playable.title, duration=playable.duration
  )
  applyOverrides(options, args)
  return startPlayback(playerModule, playable.path, options)


def handleCache(args: argparse.Namespace) -> int:
  """ダウンロード済み動画の一覧表示と削除を行う."""
  if args.clear:
    removedCount, removedSize = source.clearCache()
    if removedCount == 0:
      print("削除するキャッシュはありません．")
    else:
      print(f"{removedCount}件（{formatBytes(removedSize)}）を削除しました．")
    return EXIT_OK

  files = source.cachedFiles()
  print(f"保存先: {config.cacheDir()}")
  if not files:
    print("キャッシュはありません．")
    return EXIT_OK

  totalSize = 0
  for filePath in files:
    fileSize = filePath.stat().st_size
    totalSize += fileSize
    print(f"  {filePath.name}  {formatBytes(fileSize)}")

  print(f"合計 {len(files)}件  {formatBytes(totalSize)}")
  print(f"削除するには `{config.commandName()} cache --clear` を実行してください．")
  return EXIT_OK


def formatBytes(sizeInBytes: int) -> str:
  """バイト数を読みやすい単位へ変換する."""
  size = float(sizeInBytes)
  for unit in BYTE_UNITS:
    if size < BYTES_PER_UNIT or unit == BYTE_UNITS[-1]:
      return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
    size /= BYTES_PER_UNIT
  return f"{size:.1f} {BYTE_UNITS[-1]}"


def resolvePlaybackSource(entry: VideoEntry, args: argparse.Namespace):
  """登録内容から，実際に再生する入力を決める."""
  quality, useCache, cookies = sourceSettings(args, entry)

  if entry.isRemote and useCache:
    cachedFile = entry.cachedFile()
    if cachedFile is not None:
      # ダウンロード済みなら，ネットワークに接続せずそのまま再生する
      notifyProgress(f"ダウンロード済みの動画を再生します: {cachedFile}")
      return source.PlayableSource(path=str(cachedFile), title=entry.name)

  # URLの直リンクは時間で失効するため，再生のたびに解決し直す
  playable = source.openSource(
    entry.path, quality, useCache, notifyProgress, cookies
  )

  if entry.isRemote and useCache and not playable.isRemote:
    # 次回以降に再利用できるよう，保存先を登録内容へ記録する
    Registry().update(entry.name, {"cachedPath": playable.path})

  return playable


def sourceSettings(
  args: argparse.Namespace, entry: VideoEntry | None = None
) -> tuple[str | None, bool, source.AccessOptions]:
  """URLの解決に使う画質・キャッシュ・Cookieの設定を決める."""
  quality = valueOr(getattr(args, "quality", UNSET), entry.quality if entry else None)
  useCache = valueOr(getattr(args, "cache", UNSET), entry.cache if entry else False)
  cookies = source.AccessOptions.resolve(
    valueOr(
      getattr(args, "cookiesFromBrowser", UNSET),
      entry.cookiesFromBrowser if entry else None,
    ),
    valueOr(
      getattr(args, "cookiesFile", UNSET), entry.cookiesFile if entry else None
    ),
    valueOr(
      getattr(args, "playerClient", UNSET), entry.playerClient if entry else None
    ),
  )
  return quality, bool(useCache), cookies


def notifyProgress(message: str) -> None:
  """再生前の進捗を標準エラー出力へ表示する（映像の出力を汚さないため）."""
  print(message, file=sys.stderr)


def applyOverrides(options: Any, args: argparse.Namespace) -> None:
  """コマンドラインで指定された項目だけを再生設定へ反映する."""
  for attribute in PLAYBACK_ATTRIBUTES:
    value = getattr(args, attribute, UNSET)
    if not isinstance(value, _Unset):
      setattr(options, attribute, value)


def importPlayerModule():
  """再生モジュールを読み込む．OpenCV が無い場合は分かりやすいエラーにする."""
  try:
    from . import player as playerModule
  except ImportError as error:
    raise FraTermError(
      f"動画の再生に必要なライブラリを読み込めません（{error}）．",
      hint="`python -m pip install opencv-python numpy` を実行してください．",
    ) from error
  return playerModule


def startPlayback(playerModule, videoPath: str, options: Any) -> int:
  """再生を開始する．必要に応じて事前に警告を表示する."""
  from .renderer import supportsTrueColor

  if options.mode in (config.MODE_COLOR, config.MODE_MONO) and not supportsTrueColor():
    print(
      "警告: このターミナルは24bitカラーに対応していない可能性があります．"
      "表示が乱れる場合は --mode ascii を使用してください．",
      file=sys.stderr,
    )

  playerModule.Player(videoPath, options).play()
  return EXIT_OK


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------


def printError(error: FraTermError) -> None:
  """エラー内容と対処方法を標準エラー出力へ表示する."""
  print(f"エラー: {error.message}", file=sys.stderr)
  if error.hint:
    print(error.hint, file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
  """CLIのエントリポイント．終了コードを返す."""
  rawArgs = list(sys.argv[1:] if argv is None else argv)
  parser = buildParser()

  if not rawArgs:
    parser.print_help()
    return EXIT_OK

  args = parser.parse_args(expandImplicitPlay(rawArgs))
  handler = getattr(args, "handler", None)
  if handler is None:
    parser.print_help()
    return EXIT_ERROR

  try:
    return handler(args)
  except FraTermError as error:
    printError(error)
    return EXIT_ERROR
  except KeyboardInterrupt:
    # Ctrl+C は異常終了ではなく，利用者による中断として扱う
    return EXIT_INTERRUPTED


if __name__ == "__main__":  # pragma: no cover
  sys.exit(main())
