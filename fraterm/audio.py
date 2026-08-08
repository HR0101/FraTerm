"""FFmpeg の ffplay を使って音声を再生するモジュール."""

from __future__ import annotations

import atexit
import shutil
import subprocess

from . import config
from .errors import AudioError

FFPLAY_COMMAND = "ffplay"

# atempo フィルタが一度に扱える再生速度の範囲
MIN_TEMPO = 0.5
MAX_TEMPO = 2.0

# プロセス終了を待つ最大時間（秒）
TERMINATE_TIMEOUT = 1.0


def isAvailable() -> bool:
  """ffplay が実行可能かどうかを返す."""
  return shutil.which(FFPLAY_COMMAND) is not None


def ensureAvailable() -> None:
  """ffplay が無い場合に，導入方法を添えたエラーを送出する."""
  if isAvailable():
    return
  raise AudioError(
    "音声再生に必要な ffplay が見つかりません．",
    hint=(
      "FFmpeg を導入してください（macOS: brew install ffmpeg，"
      "Ubuntu: sudo apt install ffmpeg）．"
      "音声なしで再生する場合は --no-audio を指定してください．"
    ),
  )


def buildTempoFilter(speed: float) -> str:
  """再生速度から atempo フィルタの指定文字列を組み立てる.

  atempo は1回あたり0.5〜2.0倍までしか指定できないため，
  範囲外の速度は複数のフィルタを連結して表現する.
  """
  filters: list[str] = []
  remainingSpeed = float(speed)

  while remainingSpeed > MAX_TEMPO:
    filters.append(f"atempo={MAX_TEMPO}")
    remainingSpeed /= MAX_TEMPO
  while remainingSpeed < MIN_TEMPO:
    filters.append(f"atempo={MIN_TEMPO}")
    remainingSpeed /= MIN_TEMPO

  filters.append(f"atempo={remainingSpeed:.4f}")
  return ",".join(filters)


class AudioPlayer:
  """動画ファイルの音声を ffplay の別プロセスで再生するクラス."""

  def __init__(self, videoPath: str) -> None:
    self.videoPath = videoPath
    self._process: subprocess.Popen | None = None
    # 異常終了時にも音声プロセスが残らないようにする
    atexit.register(self.stop)

  # ---------------------------------------------------------------------
  # 再生制御
  # ---------------------------------------------------------------------

  def start(
    self,
    position: float = 0.0,
    speed: float = 1.0,
    volume: int = config.DEFAULT_VOLUME,
  ) -> None:
    """指定位置から音声再生を開始する．すでに再生中なら一度停止する."""
    ensureAvailable()
    self.stop()

    clampedVolume = max(config.MIN_VOLUME, min(config.MAX_VOLUME, int(volume)))

    command = [
      FFPLAY_COMMAND,
      "-nodisp",  # 映像ウィンドウを表示しない
      "-autoexit",  # 再生し終えたら終了する
      "-vn",  # 映像ストリームを読み込まない
      "-loglevel",
      "quiet",
      "-volume",
      str(clampedVolume),
      "-ss",
      f"{max(0.0, position):.3f}",
    ]

    if abs(speed - 1.0) > 1e-6:
      command.extend(["-af", buildTempoFilter(speed)])

    command.append(self.videoPath)

    try:
      self._process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
      )
    except OSError as error:
      self._process = None
      raise AudioError(f"音声再生を開始できません（{error}）") from error

  def stop(self) -> None:
    """音声再生を停止する．プロセスが残らないよう確実に終了させる."""
    process = self._process
    self._process = None
    if process is None or process.poll() is not None:
      return

    try:
      process.terminate()
      process.wait(timeout=TERMINATE_TIMEOUT)
    except subprocess.TimeoutExpired:
      process.kill()
      try:
        process.wait(timeout=TERMINATE_TIMEOUT)
      except subprocess.TimeoutExpired:
        pass
    except OSError:
      pass

  def isPlaying(self) -> bool:
    """音声プロセスが動作中かどうかを返す."""
    return self._process is not None and self._process.poll() is None
