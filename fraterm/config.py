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

# 設定ディレクトリを明示的に差し替えるための環境変数（テストや持ち運び用）
HOME_ENV_VAR = "FRATERM_HOME"

REGISTRY_FILE_NAME = "videos.json"

# ---------------------------------------------------------------------------
# 描画モード
# ---------------------------------------------------------------------------

MODE_ASCII = "ascii"
MODE_COLOR = "color"
MODE_MONO = "mono"
AVAILABLE_MODES = (MODE_ASCII, MODE_COLOR, MODE_MONO)
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


def resolveCharset(value: str | None) -> str:
  """プリセット名または文字列そのものを，実際に使用する文字セットへ変換する."""
  if value is None:
    return DEFAULT_CHARSET
  if value in CHARSET_PRESETS:
    return CHARSET_PRESETS[value]
  return value
