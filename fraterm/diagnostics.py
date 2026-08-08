"""動作環境と依存ツールの状態を調べるモジュール."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

from . import audio, config, settings, source

# 状態を表す記号
# 端末によって幅が変わる絵文字は使わない
STATUS_OK = "✓"
STATUS_MISSING = "!"

# バージョン確認コマンドを打ち切るまでの秒数
VERSION_TIMEOUT = 5


@dataclass
class DiagnosticItem:
  """診断結果1件を表すデータクラス."""

  label: str
  detail: str
  available: bool
  hint: str = ""

  def statusMark(self) -> str:
    """状態を表す記号を返す."""
    return STATUS_OK if self.available else STATUS_MISSING


def commandVersion(command: str, arguments: list[str] | None = None) -> str | None:
  """外部コマンドのバージョン文字列を取得する．無ければ None を返す."""
  executable = shutil.which(command)
  if executable is None:
    return None

  try:
    completed = subprocess.run(
      [executable, *(arguments or ["--version"])],
      capture_output=True,
      text=True,
      timeout=VERSION_TIMEOUT,
      check=False,
    )
  except (OSError, subprocess.TimeoutExpired):
    return ""

  output = (completed.stdout or completed.stderr or "").strip()
  return output.splitlines()[0] if output else ""


def _pythonLibraryItem() -> DiagnosticItem:
  """OpenCVの導入状況を調べる."""
  try:
    import cv2

    return DiagnosticItem("OpenCV", f"{cv2.__version__}", True)
  except ImportError:
    return DiagnosticItem(
      "OpenCV",
      "未導入（再生できません）",
      False,
      "python -m pip install opencv-python",
    )


def _ytdlpItem() -> DiagnosticItem:
  """yt-dlp の導入状況を調べる."""
  if not source.isAvailable():
    return DiagnosticItem(
      "yt-dlp", "未導入（URL再生ができません）", False, "python -m pip install yt-dlp"
    )

  version = commandVersion(source.YTDLP_COMMAND)
  if version is None:
    version = "モジュールとして利用可能"
  return DiagnosticItem("yt-dlp", version or "利用可能", True)


def _jsRuntimeItem() -> DiagnosticItem:
  """YouTubeの署名解読に使うJavaScriptランタイムを調べる."""
  for runtimeName in source.JS_RUNTIMES:
    if shutil.which(runtimeName) is not None:
      version = commandVersion(runtimeName) or ""
      return DiagnosticItem("JavaScript", f"{runtimeName} {version}".strip(), True)

  return DiagnosticItem(
    "JavaScript",
    "未導入（YouTubeの取得に失敗することがあります）",
    False,
    "brew install deno",
  )


def _ffplayItem() -> DiagnosticItem:
  """音声再生に使う ffplay の導入状況を調べる."""
  if not audio.isAvailable():
    return DiagnosticItem(
      "ffplay", "未導入（--audio が使えません）", False, "brew install ffmpeg"
    )
  version = commandVersion(audio.FFPLAY_COMMAND, ["-version"]) or "利用可能"
  return DiagnosticItem("ffplay", version, True)


def _nativeRendererItem() -> DiagnosticItem:
  """描画を高速化するC拡張の状態を調べる."""
  try:
    from . import renderer

    if renderer.HAS_NATIVE_RENDERER:
      return DiagnosticItem("C拡張", "有効（描画が高速です）", True)
    return DiagnosticItem(
      "C拡張", "無効（Python実装で動作中）", False, "python -m pip install -e ."
    )
  except ImportError:
    return DiagnosticItem("C拡張", "確認できません", False)


def _trueColorItem() -> DiagnosticItem:
  """端末の24bitカラー対応を調べる."""
  try:
    from .renderer import supportsTrueColor

    if supportsTrueColor():
      return DiagnosticItem("24bitカラー", "対応（--color true が使えます）", True)
    return DiagnosticItem(
      "24bitカラー", "未対応の可能性", False, "--color 256 をお使いください"
    )
  except ImportError:
    return DiagnosticItem("24bitカラー", "確認できません", False)


def collect() -> list[DiagnosticItem]:
  """すべての診断結果を集める."""
  items = [
    DiagnosticItem("Python", sys.version.split()[0], True),
    _pythonLibraryItem(),
    _ytdlpItem(),
    _jsRuntimeItem(),
    _ffplayItem(),
    _nativeRendererItem(),
    _trueColorItem(),
  ]

  items.append(DiagnosticItem("登録データ", str(config.registryPath()), True))
  items.append(DiagnosticItem("既定値の設定", str(settings.settingsPath()), True))
  items.append(DiagnosticItem("キャッシュ", str(config.cacheDir()), True))
  return items
