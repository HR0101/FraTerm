"""コマンドライン引数を解析し，各機能を呼び出すモジュール."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

from . import config
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
  {"add", "remove", "rm", "delete", "list", "ls", "show", "info", "edit", "play", "run"}
)

# 再生設定として上書きできる項目
OVERRIDABLE_ATTRIBUTES = (
  "mode",
  "audio",
  "width",
  "fps",
  "charset",
  "brightness",
  "contrast",
  "showStatus",
)

# 明るさの指定範囲
MIN_BRIGHTNESS = -1.0
MAX_BRIGHTNESS = 1.0

# コントラストの指定範囲
MIN_CONTRAST = 0.1
MAX_CONTRAST = 5.0

EPILOG = f"""使用例:
  {config.APP_NAME} add badapple ~/Videos/bad-apple.mp4 --mode ascii
  {config.APP_NAME} badapple
  {config.APP_NAME} list
  {config.APP_NAME} show badapple
  {config.APP_NAME} edit badapple --mode color --audio
  {config.APP_NAME} remove badapple
  {config.APP_NAME} run ~/Videos/sample.mp4 --mode color

再生中の操作:
  q: 終了 / space: 一時停止・再開 / r: 先頭から / m: ミュート / +,-: 再生速度
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
    prog=config.APP_NAME,
    description="動画をターミナル上でASCII・ANSIカラーとして再生するCLIツールです．",
    epilog=EPILOG,
    formatter_class=argparse.RawDescriptionHelpFormatter,
  )
  parser.add_argument(
    "--version",
    action="version",
    version=f"{config.APP_NAME} {config.VERSION}",
    help="バージョンを表示する",
  )

  subparsers = parser.add_subparsers(dest="command", metavar="コマンド")

  # add ---------------------------------------------------------------------
  addParser = subparsers.add_parser(
    "add", help="動画に名前を付けて登録する", description="動画に名前を付けて登録します．"
  )
  addParser.add_argument("name", help="登録名")
  addParser.add_argument("path", help="動画ファイルのパス")
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
    help="動画ファイルを登録せずに再生する",
    description="動画ファイルを登録せずに再生します．",
  )
  runParser.add_argument("path", help="動画ファイルのパス")
  addPlaybackArguments(runParser, includeStatus=True)
  runParser.set_defaults(handler=handleRun)

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
  """実際に指定された再生設定だけを辞書として取り出す."""
  changes: dict[str, Any] = {}
  for attribute in OVERRIDABLE_ATTRIBUTES:
    if attribute == "showStatus":
      continue  # ステータス表示は登録内容に保存しない
    value = getattr(args, attribute, UNSET)
    if not isinstance(value, _Unset):
      changes[attribute] = value
  return changes


def handleAdd(args: argparse.Namespace) -> int:
  """動画を登録する."""
  entry = VideoEntry(
    name=args.name,
    path=resolveVideoPath(args.path),
    mode=valueOr(args.mode, config.DEFAULT_MODE),
    audio=valueOr(args.audio, False),
    width=valueOr(args.width, None),
    fps=valueOr(args.fps, None),
    charset=valueOr(args.charset, None),
    brightness=valueOr(args.brightness, config.DEFAULT_BRIGHTNESS),
    contrast=valueOr(args.contrast, config.DEFAULT_CONTRAST),
  )

  Registry().add(entry, force=args.force)
  print(f"「{entry.name}」を登録しました．")
  print(f"再生するには `{config.APP_NAME} {entry.name}` を実行してください．")
  return EXIT_OK


def handleList(args: argparse.Namespace) -> int:
  """登録一覧を表示する."""
  entries = Registry().load()
  if not entries:
    print("登録されている動画はありません．")
    print(f"`{config.APP_NAME} add <登録名> <動画ファイル>` で登録できます．")
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
    ("動画ファイル", entry.path),
    ("描画モード", entry.mode),
    ("音声", "再生する" if entry.audio else "再生しない"),
    ("最大表示幅", "auto" if entry.width is None else f"{entry.width} 桁"),
    ("FPS上限", "auto" if entry.fps is None else f"{entry.fps:g}"),
    ("文字セット", charsetLabel),
    ("明るさ", f"{entry.brightness:g}"),
    ("コントラスト", f"{entry.contrast:g}"),
  ]

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
      hint=f"例: {config.APP_NAME} edit {args.name} --mode color --audio",
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
        f"ファイルを元の場所へ戻すか，`{config.APP_NAME} add {entry.name} "
        f"<新しいパス> --force` で登録し直してください．"
      ),
    )

  options = playerModule.PlaybackOptions.fromEntry(entry)
  applyOverrides(options, args)
  return startPlayback(playerModule, entry.path, options)


def handleRun(args: argparse.Namespace) -> int:
  """登録せずに動画ファイルを再生する."""
  playerModule = importPlayerModule()

  videoPath = resolveVideoPath(args.path)
  options = playerModule.PlaybackOptions(title=Path(videoPath).name)
  applyOverrides(options, args)
  return startPlayback(playerModule, videoPath, options)


def applyOverrides(options: Any, args: argparse.Namespace) -> None:
  """コマンドラインで指定された項目だけを再生設定へ反映する."""
  for attribute in OVERRIDABLE_ATTRIBUTES:
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
