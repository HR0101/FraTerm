"""動画を読み込み，ターミナルへ再生するモジュール."""

from __future__ import annotations

import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from . import audio as audioModule
from . import config, renderer
from .errors import PlaybackError, VideoFileError
from .keyboard import KeyReader
from .registry import VideoEntry
from .textwidth import truncateToWidth

# ターミナル制御用のエスケープシーケンス
ESC = "\x1b"
ENTER_ALT_SCREEN = f"{ESC}[?1049h"
LEAVE_ALT_SCREEN = f"{ESC}[?1049l"
HIDE_CURSOR = f"{ESC}[?25l"
SHOW_CURSOR = f"{ESC}[?25h"
CLEAR_SCREEN = f"{ESC}[2J"
CURSOR_HOME = f"{ESC}[H"
CLEAR_LINE = f"{ESC}[K"
RESET_ATTRIBUTES = f"{ESC}[0m"
DIM = f"{ESC}[2m"

# 再生中に表示する操作説明
KEY_HELP = "[q]終了 [space]一時停止 [r]先頭 [m]音声 [+/-]速度"

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600


@dataclass
class PlaybackOptions:
  """1回の再生に使用する設定をまとめたデータクラス."""

  mode: str = config.DEFAULT_MODE
  audio: bool = False
  width: int | None = None
  fps: float | None = None
  charset: str | None = None
  brightness: float = config.DEFAULT_BRIGHTNESS
  contrast: float = config.DEFAULT_CONTRAST
  showStatus: bool = True
  title: str = ""

  @classmethod
  def fromEntry(cls, entry: VideoEntry) -> "PlaybackOptions":
    """登録情報から再生設定を作る."""
    return cls(
      mode=entry.mode,
      audio=entry.audio,
      width=entry.width,
      fps=entry.fps,
      charset=entry.charset,
      brightness=entry.brightness,
      contrast=entry.contrast,
      title=entry.name,
    )


def formatTime(seconds: float) -> str:
  """秒数を MM:SS または H:MM:SS の形式へ変換する."""
  if seconds < 0 or seconds != seconds:  # 負値と NaN を除外する
    return "--:--"

  totalSeconds = int(seconds)
  hours = totalSeconds // SECONDS_PER_HOUR
  minutes = (totalSeconds % SECONDS_PER_HOUR) // SECONDS_PER_MINUTE
  remainder = totalSeconds % SECONDS_PER_MINUTE
  if hours > 0:
    return f"{hours}:{minutes:02d}:{remainder:02d}"
  return f"{minutes:02d}:{remainder:02d}"


class Player:
  """動画1本をターミナルへ再生するクラス."""

  def __init__(
    self,
    videoPath: str | Path,
    options: PlaybackOptions | None = None,
    stream: TextIO | None = None,
  ) -> None:
    self.videoPath = str(videoPath)
    self.options = options or PlaybackOptions()
    self.stream = stream or sys.stdout

    # 再生状態
    self._speed = 1.0
    self._paused = False
    self._muted = not self.options.audio
    self._mediaBase = 0.0
    self._clockStart = 0.0

    # 再生中に使用する内部状態
    self._capture = None
    self._videoFps = config.FALLBACK_FPS
    self._duration = 0.0
    self._nextFrameIndex = 0
    self._lastRenderedMedia: float | None = None
    self._lastSize: tuple[int, int] | None = None
    self._audioPlayer: audioModule.AudioPlayer | None = None

  # -------------------------------------------------------------------------
  # 再生の入口
  # -------------------------------------------------------------------------

  def play(self) -> None:
    """動画を最後まで（または利用者が終了するまで）再生する."""
    import cv2  # 起動を軽くするため，再生時にのみ読み込む

    videoFile = Path(self.videoPath)
    if not videoFile.is_file():
      raise VideoFileError(
        f"動画ファイルが見つかりません: {self.videoPath}",
        hint="ファイルが移動または削除されていないか確認してください．",
      )

    # 端末を切り替える前に，音声の準備可否を確認する
    if self.options.audio:
      audioModule.ensureAvailable()
      self._audioPlayer = audioModule.AudioPlayer(self.videoPath)

    capture = cv2.VideoCapture(self.videoPath)
    if not capture.isOpened():
      raise PlaybackError(
        f"動画ファイルを読み込めません: {self.videoPath}",
        hint="対応していない形式か，ファイルが壊れている可能性があります．",
      )

    self._capture = capture
    self._videoFps = self._readFps(capture, cv2)
    self._duration = self._readDuration(capture, cv2)

    try:
      self._prepareTerminal()
      with KeyReader() as keyReader:
        self._startClock()
        self._syncAudio()
        self._runLoop(keyReader)
    finally:
      if self._audioPlayer is not None:
        self._audioPlayer.stop()
      capture.release()
      self._capture = None
      self._restoreTerminal()

  # -------------------------------------------------------------------------
  # 動画情報
  # -------------------------------------------------------------------------

  @staticmethod
  def _readFps(capture, cv2Module) -> float:
    """動画のFPSを取得する．取得できない場合は既定値を返す."""
    rawFps = capture.get(cv2Module.CAP_PROP_FPS)
    if rawFps is None or rawFps != rawFps or rawFps <= 0:
      return config.FALLBACK_FPS
    return float(rawFps)

  def _readDuration(self, capture, cv2Module) -> float:
    """動画の長さ（秒）を求める．取得できない場合は0を返す."""
    frameCount = capture.get(cv2Module.CAP_PROP_FRAME_COUNT)
    if frameCount is None or frameCount != frameCount or frameCount <= 0:
      return 0.0
    return float(frameCount) / self._videoFps

  # -------------------------------------------------------------------------
  # 再生クロック
  # -------------------------------------------------------------------------

  def _startClock(self) -> None:
    """再生位置の基準時刻を現在時刻に合わせる."""
    self._clockStart = time.perf_counter()

  def _mediaTime(self) -> float:
    """動画内の現在位置（秒）を返す．一時停止中は進まない."""
    if self._paused:
      return self._mediaBase
    return self._mediaBase + (time.perf_counter() - self._clockStart) * self._speed

  def _rebaseClock(self) -> None:
    """現在位置を基準値へ移し，速度変更や一時停止に備える."""
    self._mediaBase = self._mediaTime()
    self._startClock()

  # -------------------------------------------------------------------------
  # 音声
  # -------------------------------------------------------------------------

  def _syncAudio(self) -> None:
    """再生状態に合わせて音声プロセスを開始・停止する."""
    if self._audioPlayer is None:
      return

    if self._paused or self._muted:
      self._audioPlayer.stop()
      return

    self._audioPlayer.start(position=self._mediaTime(), speed=self._speed)

  # -------------------------------------------------------------------------
  # メインループ
  # -------------------------------------------------------------------------

  def _runLoop(self, keyReader: KeyReader) -> None:
    """フレームの取得・描画・待機を繰り返す."""
    while True:
      if not self._processPendingKeys(keyReader):
        return

      if self._paused:
        # 一時停止中も入力を取りこぼさないよう，待機で読んだキーを必ず処理する
        self._drawStatusOnly()
        key = keyReader.readKey(config.PAUSED_POLL_INTERVAL)
        if key is not None and not self._handleKey(key):
          return
        continue

      if not self._advanceToTargetFrame():
        return

      frameTime = self._nextFrameIndex / self._videoFps
      waitSeconds = (frameTime - self._mediaTime()) / self._speed
      if waitSeconds > 0:
        # 次のフレームの表示時刻まで待つ．待機中もキー入力を受け付ける
        key = keyReader.readKey(min(waitSeconds, config.MAX_SLEEP_INTERVAL))
        if key is not None and not self._handleKey(key):
          return
        continue

      if self._shouldSkipRender(frameTime):
        if not self._grabFrame():
          return
        continue

      frame = self._readFrame()
      if frame is None:
        return

      self._lastRenderedMedia = frameTime
      self._drawFrame(frame)

  def _processPendingKeys(self, keyReader: KeyReader) -> bool:
    """溜まっているキー入力をすべて処理する．終了要求があれば偽を返す."""
    while True:
      key = keyReader.readKey(0.0)
      if key is None:
        return True
      if not self._handleKey(key):
        return False

  def _advanceToTargetFrame(self) -> bool:
    """処理が遅れている場合に，表示予定のフレームまで読み飛ばす."""
    targetIndex = int(self._mediaTime() * self._videoFps)
    while self._nextFrameIndex < targetIndex:
      if not self._grabFrame():
        return False
    return True

  def _shouldSkipRender(self, frameTime: float) -> bool:
    """FPS上限の指定により，このフレームの描画を省くべきかどうかを返す."""
    fpsLimit = self.options.fps
    if not fpsLimit or fpsLimit <= 0:
      return False
    if self._lastRenderedMedia is None:
      return False
    return (frameTime - self._lastRenderedMedia) < (1.0 / fpsLimit)

  def _grabFrame(self) -> bool:
    """フレームをデコードせずに1つ読み進める."""
    if self._capture is None or not self._capture.grab():
      return False
    self._nextFrameIndex += 1
    return True

  def _readFrame(self):
    """フレームを1つ読み込む．動画の終端では None を返す."""
    if self._capture is None:
      return None
    isRead, frame = self._capture.read()
    if not isRead or frame is None:
      return None
    self._nextFrameIndex += 1
    return frame

  # -------------------------------------------------------------------------
  # キー操作
  # -------------------------------------------------------------------------

  def _handleKey(self, key: str) -> bool:
    """キー入力に応じて再生状態を変更する．終了する場合は偽を返す."""
    lowerKey = key.lower()

    if lowerKey == "q" or key == "\x03":  # Ctrl+C も終了として扱う
      return False

    if key == " ":
      self._togglePause()
      return True

    if lowerKey == "r":
      self._restart()
      return True

    if lowerKey == "m":
      self._toggleMute()
      return True

    if key in ("+", "="):
      self._changeSpeed(config.SPEED_STEP)
      return True

    if key in ("-", "_"):
      self._changeSpeed(-config.SPEED_STEP)
      return True

    return True

  def _togglePause(self) -> None:
    """一時停止と再開を切り替える."""
    if self._paused:
      self._paused = False
      self._startClock()
    else:
      self._rebaseClock()
      self._paused = True
    self._syncAudio()

  def _restart(self) -> None:
    """再生位置を先頭へ戻す."""
    import cv2

    if self._capture is not None:
      self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
    self._nextFrameIndex = 0
    self._lastRenderedMedia = None
    self._mediaBase = 0.0
    self._startClock()
    self._syncAudio()

  def _toggleMute(self) -> None:
    """ミュートを切り替える．音声を使わない再生では何もしない."""
    if self._audioPlayer is None:
      return
    self._muted = not self._muted
    self._syncAudio()

  def _changeSpeed(self, delta: float) -> None:
    """再生速度を変更する．上下限を超えないように丸める."""
    newSpeed = round(self._speed + delta, 2)
    newSpeed = min(config.MAX_SPEED, max(config.MIN_SPEED, newSpeed))
    if newSpeed == self._speed:
      return

    self._rebaseClock()
    self._speed = newSpeed
    self._syncAudio()

  # -------------------------------------------------------------------------
  # 描画
  # -------------------------------------------------------------------------

  def _prepareTerminal(self) -> None:
    """代替画面へ切り替え，カーソルを隠す."""
    if not self._isInteractiveStream():
      return
    self.stream.write(ENTER_ALT_SCREEN + HIDE_CURSOR + CLEAR_SCREEN)
    self.stream.flush()

  def _restoreTerminal(self) -> None:
    """カーソルと画面の状態を必ず元へ戻す."""
    if not self._isInteractiveStream():
      # パイプ出力でも文字色は戻しておく
      try:
        self.stream.write(RESET_ATTRIBUTES + "\n")
        self.stream.flush()
      except (ValueError, OSError):
        pass
      return

    try:
      self.stream.write(RESET_ATTRIBUTES + SHOW_CURSOR + LEAVE_ALT_SCREEN)
      self.stream.flush()
    except (ValueError, OSError):
      pass

  def _isInteractiveStream(self) -> bool:
    """出力先がターミナルかどうかを返す."""
    try:
      return bool(self.stream.isatty())
    except (AttributeError, ValueError):
      return False

  def _terminalSize(self) -> tuple[int, int]:
    """ターミナルの桁数と行数を返す."""
    size = shutil.get_terminal_size(config.FALLBACK_TERMINAL_SIZE)
    return size.columns, size.lines

  def _drawFrame(self, frame) -> None:
    """1フレーム分の文字列を組み立てて出力する."""
    frameHeight, frameWidth = frame.shape[:2]
    terminalWidth, terminalHeight = self._terminalSize()
    columns, rows = renderer.computeSize(
      frameWidth,
      frameHeight,
      terminalWidth,
      terminalHeight,
      maxWidth=self.options.width,
    )

    parts: list[str] = []
    currentSize = (columns, rows, terminalWidth, terminalHeight)
    if currentSize != self._lastSize:
      # サイズが変わったときだけ画面を消し，残像を防ぐ
      parts.append(CLEAR_SCREEN)
      self._lastSize = currentSize

    frameText = renderer.renderFrame(
      frame,
      self.options.mode,
      columns,
      rows,
      config.resolveCharset(self.options.charset),
      self.options.brightness,
      self.options.contrast,
    )

    parts.append(CURSOR_HOME)
    parts.append(frameText.replace("\n", f"{CLEAR_LINE}\n"))
    parts.append(CLEAR_LINE)

    if self.options.showStatus:
      parts.append(self._statusText(rows, terminalWidth))

    self._write("".join(parts))

  def _drawStatusOnly(self) -> None:
    """一時停止中に，ステータス行だけを更新する."""
    if not self.options.showStatus or self._lastSize is None:
      return
    _, rows, terminalWidth, _ = self._lastSize
    self._write(self._statusText(rows, terminalWidth))

  def _statusText(self, rows: int, terminalWidth: int) -> str:
    """画面下部に表示するステータス行を組み立てる."""
    state = "一時停止" if self._paused else "再生中"
    position = formatTime(self._mediaTime())
    total = formatTime(self._duration) if self._duration > 0 else "--:--"
    audioState = "-" if self._audioPlayer is None else ("消音" if self._muted else "on")
    title = self.options.title or Path(self.videoPath).name

    body = (
      f"{state} {title}  {position}/{total}  x{self._speed:.2f}  "
      f"{self.options.mode}  音声:{audioState}  {KEY_HELP}"
    )
    body = truncateToWidth(body, max(0, terminalWidth))

    # ステータス行は描画領域のすぐ下（1始まりの行番号）へ表示する
    return f"{ESC}[{rows + 1};1H{DIM}{body}{RESET_ATTRIBUTES}{CLEAR_LINE}"

  def _write(self, text: str) -> None:
    """出力先へ書き込む．端末が閉じられている場合は再生を終了させる."""
    try:
      self.stream.write(text)
      self.stream.flush()
    except (BrokenPipeError, ValueError):
      raise PlaybackError("出力先へ書き込めなくなったため再生を終了します．")
