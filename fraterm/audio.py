"""FFmpeg の ffplay を使って音声を再生するモジュール."""

from __future__ import annotations

import atexit
import math
import re
import shutil
import subprocess
import threading
import time

from . import config
from .errors import AudioError

FFPLAY_COMMAND = "ffplay"

# atempo フィルタが一度に扱える再生速度の範囲
MIN_TEMPO = 0.5
MAX_TEMPO = 2.0

# プロセス終了を待つ最大時間（秒）
TERMINATE_TIMEOUT = 1.0

# ffplay の進捗表示から音声クロックを取り出す．音声だけを再生する場合も
# ``-stats`` の先頭に現在位置と ``M-A``（音声との差）が出力される．
AUDIO_STATUS_PATTERN = re.compile(
  r"(?P<position>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s+M-A:"
)


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


def audioPositionFromStatus(status: str) -> float | None:
  """ffplayの進捗行から音声のメディア位置を取り出す."""
  match = AUDIO_STATUS_PATTERN.search(status)
  if match is None:
    return None
  position = float(match.group("position"))
  return position if math.isfinite(position) else None


class AudioPlayer:
  """動画ファイルの音声を ffplay の別プロセスで再生するクラス."""

  def __init__(self, videoPath: str) -> None:
    self.videoPath = videoPath
    self._process: subprocess.Popen | None = None
    self._readyEvent = threading.Event()
    self._statusLock = threading.Lock()
    self._lastAudioPosition: float | None = None
    self._stderrThread: threading.Thread | None = None
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
    self._readyEvent.clear()
    with self._statusLock:
      self._lastAudioPosition = None

    clampedVolume = max(config.MIN_VOLUME, min(config.MAX_VOLUME, int(volume)))

    command = [
      FFPLAY_COMMAND,
      "-nodisp",  # 映像ウィンドウを表示しない
      "-autoexit",  # 再生し終えたら終了する
      "-vn",  # 映像ストリームを読み込まない
      "-stats",  # 音声クロックを取得し，映像側の開始時刻を合わせる
      "-loglevel",
      "error",
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
        stderr=subprocess.PIPE,
      )
    except OSError as error:
      self._process = None
      raise AudioError(f"音声再生を開始できません（{error}）") from error

    if self._process.stderr is not None:
      self._stderrThread = threading.Thread(
        target=self._readStatus,
        args=(self._process, self._process.stderr),
        name="fraterm-audio-status",
        daemon=True,
      )
      self._stderrThread.start()

  def _readStatus(self, process, stream) -> None:
    """ffplayの進捗出力を読み，音声クロックが動き始めたら通知する."""
    pending = ""
    try:
      readChunk = getattr(stream, "read1", stream.read)
      while process.poll() is None:
        chunk = readChunk(4096)
        if not chunk:
          break
        pending += chunk.decode("utf-8", errors="replace")
        while True:
          separators = [
            index
            for index in (pending.find("\r"), pending.find("\n"))
            if index >= 0
          ]
          if not separators:
            break
          separatorIndex = min(separators)
          status = pending[:separatorIndex]
          pending = pending[separatorIndex + 1 :]
          self._recordStatus(status)
      self._recordStatus(pending)
    except (OSError, ValueError):
      # 停止時にパイプが閉じられた場合は通常の終了として扱う
      pass

  def _recordStatus(self, status: str) -> None:
    """1行分のffplay出力から音声位置を記録する."""
    position = audioPositionFromStatus(status)
    if position is None:
      return
    with self._statusLock:
      self._lastAudioPosition = position
    self._readyEvent.set()

  def waitUntilReady(self, timeout: float = config.AUDIO_READY_TIMEOUT) -> float | None:
    """音声クロックが動き始めるまで待ち，その時点の位置を返す."""
    process = self._process
    if process is None:
      return None

    deadline = time.monotonic() + max(0.0, float(timeout))
    while not self._readyEvent.is_set():
      if process.poll() is not None:
        break
      remaining = deadline - time.monotonic()
      if remaining <= 0:
        break
      self._readyEvent.wait(min(0.05, remaining))

    with self._statusLock:
      return self._lastAudioPosition

  def stop(self) -> None:
    """音声再生を停止する．プロセスが残らないよう確実に終了させる."""
    process = self._process
    self._process = None
    if process is not None and process.poll() is None:
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

    stderr = getattr(process, "stderr", None) if process is not None else None
    if stderr is not None:
      try:
        stderr.close()
      except OSError:
        pass
    statusThread = self._stderrThread
    self._stderrThread = None
    self._readyEvent.set()
    if statusThread is not None and statusThread is not threading.current_thread():
      statusThread.join(timeout=TERMINATE_TIMEOUT)

  def isPlaying(self) -> bool:
    """音声プロセスが動作中かどうかを返す."""
    return self._process is not None and self._process.poll() is None
