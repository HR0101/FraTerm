"""設定ファイルの場所とアプリ全体で共有する定数を定義するモジュール."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# アプリケーション情報
# ---------------------------------------------------------------------------

APP_NAME = "fraterm"
VERSION = "0.1.0"

# 短く打てるようにする別名
SHORT_COMMAND_NAME = "ft"

# 実行時のコマンド名として認める値
COMMAND_ALIASES = (APP_NAME, SHORT_COMMAND_NAME)

# 設定ディレクトリを明示的に差し替えるための環境変数（テストや持ち運び用）
HOME_ENV_VAR = "FRATERM_HOME"

REGISTRY_FILE_NAME = "videos.json"

# ダウンロードした動画を保存するディレクトリ名
CACHE_DIR_NAME = "cache"

# ---------------------------------------------------------------------------
# URL再生（yt-dlp）
# ---------------------------------------------------------------------------

# 端末表示ではそれほど高い解像度を必要としないため，既定は480pとする
DEFAULT_QUALITY = "480"
QUALITY_CHOICES = ("360", "480", "720", "1080", "best", "worst")

# URLとして扱うスキーム
URL_SCHEMES = ("http://", "https://")

# yt-dlp がCookieを読み出せるブラウザ
SUPPORTED_COOKIE_BROWSERS = (
  "brave",
  "chrome",
  "chromium",
  "edge",
  "firefox",
  "opera",
  "safari",
  "vivaldi",
  "whale",
)

# Cookieの指定を毎回書かずに済ませるための環境変数
COOKIES_BROWSER_ENV_VAR = "FRATERM_COOKIES_FROM_BROWSER"
COOKIES_FILE_ENV_VAR = "FRATERM_COOKIES"

# YouTubeの取得方法（プレイヤークライアント）としてよく使う値
COMMON_PLAYER_CLIENTS = ("mweb", "tv", "web", "web_safari", "tv_embedded", "ios")


def isUrl(text: str) -> bool:
  """文字列がURLかどうかを判定する."""
  return text.strip().lower().startswith(URL_SCHEMES)

# ---------------------------------------------------------------------------
# 描画モード
# ---------------------------------------------------------------------------

MODE_ASCII = "ascii"
MODE_EDGE = "edge"
MODE_COLOR = "color"
MODE_MONO = "mono"
AVAILABLE_MODES = (MODE_ASCII, MODE_EDGE, MODE_COLOR, MODE_MONO)
DEFAULT_MODE = MODE_ASCII

# 上下2画素を1文字で表現するモード（ハーフブロック文字を使用する）
HALF_BLOCK_MODES = (MODE_COLOR, MODE_MONO)

# ---------------------------------------------------------------------------
# 文字セット
# ---------------------------------------------------------------------------

# 暗い画素から明るい画素の順に並べる
CHARSET_PRESETS = {
  "standard": " .,:;irsXA253hMHGS#9B&@",
  "simple": " .:-=+*#%@",
  "blocks": " ░▒▓█",
  "minimal": " .*#",
}
DEFAULT_CHARSET_NAME = "standard"
DEFAULT_CHARSET = CHARSET_PRESETS[DEFAULT_CHARSET_NAME]

# 輪郭モードでは線が目立つよう，塗りつぶしに薄い文字セットを使う
DEFAULT_EDGE_CHARSET = " .:"

# ---------------------------------------------------------------------------
# 輪郭検出（edgeモード）
# ---------------------------------------------------------------------------

# 1文字あたり何画素で線の向きを判定するか
EDGE_SAMPLE_FACTOR = 3

# 上位何パーセントの勾配を線として扱うか（フレームごとに自動調整する）
EDGE_PERCENTILE = 80.0

# 平坦な映像でノイズを線として拾わないための下限値
EDGE_MIN_THRESHOLD = 70.0

# セル内で線と判定された画素がこの割合を超えたら，そのセルを線として描く
EDGE_MIN_RATIO = 0.4

# ---------------------------------------------------------------------------
# 描画パラメータ
# ---------------------------------------------------------------------------

# ターミナルの文字セルは横1に対して縦がおよそ2倍の高さを持つ
CELL_ASPECT_RATIO = 2.0

# 動画からFPSを取得できなかった場合に使用する値
FALLBACK_FPS = 30.0

# 描画に確保する最小サイズ
MIN_COLUMNS = 8
MIN_ROWS = 4

# 画面下部にステータス行として確保する行数
STATUS_ROW_COUNT = 1

# ターミナルサイズを取得できなかった場合の既定値
FALLBACK_TERMINAL_SIZE = (80, 24)

DEFAULT_BRIGHTNESS = 0.0
DEFAULT_CONTRAST = 1.0

# ---------------------------------------------------------------------------
# 再生制御
# ---------------------------------------------------------------------------

MIN_SPEED = 0.25
MAX_SPEED = 4.0
SPEED_STEP = 0.25

# 一時停止中にキー入力を待つ間隔（秒）
PAUSED_POLL_INTERVAL = 0.05

# 1回の待機で連続してスリープする最大時間（秒）．キー入力の反応を保つ
MAX_SLEEP_INTERVAL = 0.1

# ---------------------------------------------------------------------------
# 設定ファイルの位置
# ---------------------------------------------------------------------------


def commandName() -> str:
  """実際に打たれたコマンド名を返す．別名で起動した場合はその名前を使う."""
  invokedName = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else ""
  # 想定外の実行方法（python -m など）では正式名称を使う
  return invokedName if invokedName in COMMAND_ALIASES else APP_NAME


def configDir() -> Path:
  """OSごとに適切な設定ディレクトリのパスを返す."""
  overridePath = os.environ.get(HOME_ENV_VAR)
  if overridePath:
    return Path(overridePath).expanduser()

  if sys.platform == "darwin":
    return Path.home() / "Library" / "Application Support" / APP_NAME

  if sys.platform.startswith("win"):
    appData = os.environ.get("APPDATA")
    baseDir = Path(appData) if appData else Path.home() / "AppData" / "Roaming"
    return baseDir / APP_NAME

  xdgConfigHome = os.environ.get("XDG_CONFIG_HOME")
  baseDir = Path(xdgConfigHome) if xdgConfigHome else Path.home() / ".config"
  return baseDir / APP_NAME


def registryPath() -> Path:
  """登録情報を保存するJSONファイルのパスを返す."""
  return configDir() / REGISTRY_FILE_NAME


def cacheDir() -> Path:
  """ダウンロードした動画を保存するディレクトリのパスを返す."""
  return configDir() / CACHE_DIR_NAME


def resolveCharset(value: str | None) -> str:
  """プリセット名または文字列そのものを，実際に使用する文字セットへ変換する."""
  if value is None:
    return DEFAULT_CHARSET
  if value in CHARSET_PRESETS:
    return CHARSET_PRESETS[value]
  return value


def charsetFor(mode: str, value: str | None) -> str:
  """描画モードに応じた既定値を考慮して，使用する文字セットを決める."""
  if value is None and mode == MODE_EDGE:
    return DEFAULT_EDGE_CHARSET
  return resolveCharset(value)
