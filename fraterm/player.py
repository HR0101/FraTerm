"""動画を読み込み，ターミナルへ再生するモジュール."""

from __future__ import annotations

import shutil
import signal
import struct
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, TextIO

from . import audio as audioModule
from . import config, renderer
from .errors import PlaybackError, VideoFileError
from .frame_reader import FrameReader
from .keyboard import KEY_LEFT, KEY_RIGHT, KeyReader
from .registry import VideoEntry
from .textwidth import sanitizeText, truncateToWidth

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

# 後始末を必要とする終了シグナル（Windows に無いものは実行時に読み飛ばす）
TERMINATION_SIGNALS = ("SIGTERM", "SIGHUP")

# 再生中に表示する操作説明
KEY_HELP = "[q/Esc]終了 [space]一時停止 [←/→]移動 [r]先頭 [m]消音 [+/-]速度 [9/0]音量 [s]保存"

# エラー表示でURLを短く見せるときの幅
MAX_SOURCE_LABEL_WIDTH = 60

# 保存名として受け付ける最大文字数
MAX_INPUT_LENGTH = 40

# 入力待ちの間隔（秒）
PROMPT_POLL_INTERVAL = 0.1

# 保存結果のメッセージを表示しておく最大秒数
MESSAGE_DISPLAY_SECONDS = 6.0

# 入力の確定・取り消し・1文字削除に使うキー
ENTER_KEYS = ("\r", "\n")
BACKSPACE_KEYS = ("\x7f", "\x08")

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600

# 再生開始前に動画全体の黒帯を確認する代表サンプル数
BORDER_SCAN_SAMPLES = 12


class RenderedFrameStore:
  """事前生成したフレーム文字列を一時ファイルへ保存する."""

  _HEADER = struct.Struct(">Q")

  def __init__(self) -> None:
    self._file: BinaryIO = tempfile.TemporaryFile(mode="w+b")
    self._offsets: list[int] = []

  def append(self, frameText: str) -> None:
    """フレームを末尾へ追加する."""
    payload = frameText.encode("utf-8")
    self._offsets.append(self._file.tell())
    self._file.write(self._HEADER.pack(len(payload)))
    self._file.write(payload)

  def read(self, frameIndex: int) -> str | None:
    """指定番号のフレームを読み込む．範囲外なら None を返す."""
    if frameIndex < 0 or frameIndex >= len(self._offsets):
      return None
    self._file.seek(self._offsets[frameIndex])
    header = self._file.read(self._HEADER.size)
    if len(header) != self._HEADER.size:
      return None
    payloadSize = self._HEADER.unpack(header)[0]
    payload = self._file.read(payloadSize)
    if len(payload) != payloadSize:
      return None
    return payload.decode("utf-8")

  def __len__(self) -> int:
    return len(self._offsets)

  def close(self) -> None:
    """一時ファイルを閉じて削除する."""
    self._file.close()


@dataclass
class PlaybackOptions:
  """1回の再生に使用する設定をまとめたデータクラス."""

  mode: str = config.DEFAULT_MODE
  audio: bool = False
  width: int | None = None
  fps: float | None = None
  # 再生開始前に全フレームを文字列へ変換しておくかどうか
  preRender: bool = False
  charset: str | None = None
  brightness: float = config.DEFAULT_BRIGHTNESS
  contrast: float = config.DEFAULT_CONTRAST
  showStatus: bool = True
  # 文字に色を付けるかどうか（ascii・edgeモードでのみ有効）
  color: str = config.DEFAULT_COLOR
  volume: int = config.DEFAULT_VOLUME
  # 音声が遅れて聞こえる場合に前後させる秒数
  audioOffset: float = config.DEFAULT_AUDIO_OFFSET
  title: str = ""
  # 動画から長さを取得できない場合（URL再生など）に使用する再生時間
  duration: float | None = None
  # 再生中に保存する処理．登録名を受け取り，結果のメッセージを返す
  onSave: Callable[[str], str] | None = None

  @classmethod
  def fromEntry(cls, entry: VideoEntry) -> "PlaybackOptions":
    """登録情報から再生設定を作る."""
    return cls(
      mode=entry.mode,
      audio=entry.audio,
      width=entry.width,
      fps=entry.fps,
      preRender=entry.preRender,
      charset=entry.charset,
      brightness=entry.brightness,
      contrast=entry.contrast,
      color=entry.color,
      volume=entry.volume,
      audioOffset=entry.audioOffset,
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
    self._volume = self.options.volume
    self._mediaBase = 0.0
    self._clockStart = 0.0

    # 再生中に使用する内部状態
    self._capture = None
    self._frameReader: FrameReader | None = None
    self._videoFps = config.FALLBACK_FPS
    self._duration = 0.0
    self._nextFrameIndex = 0
    self._lastRenderedMedia: float | None = None
    self._lastSize: tuple[int, int, int, int] | None = None
    self._letterboxBounds: tuple[int, int, int, int] | None = None
    self._preRenderedFrames: RenderedFrameStore | None = None
    self._preRenderedLayout: tuple[int, int, int, int] | None = None
    self._audioPlayer: audioModule.AudioPlayer | None = None
    self._previousHandlers: dict = {}
    self._keyReader: KeyReader | None = None

  # -------------------------------------------------------------------------
  # 再生の入口
  # -------------------------------------------------------------------------

  def play(self) -> None:
    """動画を最後まで（または利用者が終了するまで）再生する."""
    import cv2  # 起動を軽くするため，再生時にのみ読み込む

    # URLはこの時点では存在確認できないため，ファイルのときだけ確認する
    if not config.isUrl(self.videoPath) and not Path(self.videoPath).is_file():
      raise VideoFileError(
        f"動画ファイルが見つかりません: {self.videoPath}",
        hint="ファイルが移動または削除されていないか確認してください．",
      )

    # 端末を切り替える前に，音声の準備可否を確認する
    if self.options.audio:
      audioModule.ensureAvailable()
      self._audioPlayer = audioModule.AudioPlayer(self.videoPath)

    capture = self._openCapture(cv2)

    self._capture = capture
    self._letterboxBounds = None
    self._videoFps = self._readFps(capture, cv2)
    self._duration = self._readDuration(capture, cv2)
    if self._duration <= 0 and self.options.duration:
      # ストリーミング再生ではフレーム数を取得できないため，取得済みの情報を使う
      self._duration = float(self.options.duration)

    try:
      # 動画全体で固定されている黒帯だけを再生前にクロップ対象にする
      self._letterboxBounds = self._scanPersistentBorders(capture, cv2)
      if self.options.preRender:
        # 描画処理を再生前に終え，実際の再生中は文字列の出力だけにする
        self._preRenderVideo(capture)
      else:
        # デコードを描画スレッドから分離し，端末出力の一時的な遅延を吸収する
        self._frameReader = FrameReader(capture)

      self._installSignalHandlers()
      self._prepareTerminal()
      with KeyReader() as keyReader:
        self._startClock()
        self._syncAudio()
        self._runLoop(keyReader)
    finally:
      if self._audioPlayer is not None:
        self._audioPlayer.stop()
      if self._frameReader is not None:
        self._frameReader.close()
        self._frameReader = None
      if self._preRenderedFrames is not None:
        self._preRenderedFrames.close()
        self._preRenderedFrames = None
        self._preRenderedLayout = None
      if self._capture is not None:
        self._capture.release()
        self._capture = None
      self._restoreTerminal()
      self._restoreSignalHandlers()

  # -------------------------------------------------------------------------
  # 動画を開く
  # -------------------------------------------------------------------------

  def _sourceLabel(self) -> str:
    """エラー表示に使う，短くて分かりやすい入力名を返す."""
    if not config.isUrl(self.videoPath):
      return self.videoPath
    if self.options.title:
      return self.options.title
    return truncateToWidth(self.videoPath, MAX_SOURCE_LABEL_WIDTH) + "…"

  @staticmethod
  def _quietOpenCvLogging(cv2Module) -> None:
    """OpenCVの警告表示を抑える．失敗の理由は自前のメッセージで伝える."""
    try:
      logging = cv2Module.utils.logging
      logging.setLogLevel(logging.LOG_LEVEL_ERROR)
    except AttributeError:
      # 対応していない版では何もしない
      pass

  def _openCapture(self, cv2Module):
    """動画を開く．URLは一時的に失敗することがあるため何度か試す."""
    self._quietOpenCvLogging(cv2Module)
    isRemote = config.isUrl(self.videoPath)

    # URLで自動選択に任せると，開けなかったときに連番画像として解釈し直し，
    # 本当の原因が分からないエラーになる．FFmpegを明示して防ぐ
    backend = cv2Module.CAP_FFMPEG if isRemote else cv2Module.CAP_ANY
    attempts = config.REMOTE_OPEN_ATTEMPTS if isRemote else 1

    for attempt in range(1, attempts + 1):
      capture = cv2Module.VideoCapture(self.videoPath, backend)
      if capture.isOpened():
        return capture

      capture.release()
      if attempt < attempts:
        print(
          f"読み込めなかったため再試行します（{attempt}/{attempts - 1}）．",
          file=sys.stderr,
        )
        time.sleep(config.REMOTE_OPEN_RETRY_DELAY)

    raise PlaybackError(
      f"動画を読み込めません: {self._sourceLabel()}",
      hint=(
        "通信が不安定な可能性があります．"
        "`--cache` を付けると，ダウンロードしてから再生するので安定します．"
        if isRemote
        else "対応していない形式か，ファイルが壊れている可能性があります．"
      ),
    )

  # -------------------------------------------------------------------------
  # 終了シグナルの処理
  # -------------------------------------------------------------------------

  def _installSignalHandlers(self) -> None:
    """終了シグナルを受けても後始末できるようにする.

    既定のままでは SIGTERM や SIGHUP で即座に終了してしまい，音声プロセスが
    残ったままになる．割り込みとして扱い，通常の終了処理を通す.
    """
    self._previousHandlers = {}
    for signalNumber in TERMINATION_SIGNALS:
      handler = getattr(signal, signalNumber, None)
      if handler is None:
        continue
      try:
        self._previousHandlers[handler] = signal.getsignal(handler)
        signal.signal(handler, self._onTerminationSignal)
      except (ValueError, OSError):
        # メインスレッド以外では設定できないため，その場合は何もしない
        self._previousHandlers.pop(handler, None)

  def _restoreSignalHandlers(self) -> None:
    """シグナルハンドラを元に戻す."""
    for signalNumber, previousHandler in self._previousHandlers.items():
      try:
        signal.signal(signalNumber, previousHandler)
      except (ValueError, OSError):
        pass
    self._previousHandlers = {}

  @staticmethod
  def _onTerminationSignal(signalNumber, frame) -> None:
    """終了シグナルを割り込みとして送出し，finally の後始末へつなげる."""
    raise KeyboardInterrupt

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

  @staticmethod
  def _scanPersistentBorders(capture, cv2Module):
    """動画全体から代表フレームを読み，常に黒い境界だけを返す.

    シークできないストリームやフレーム数を取得できない動画では，安全側に倒して
    クロップしない（None）．サンプル間で境界が変わる場合も，その辺は残す.
    """
    rawFrameCount = capture.get(cv2Module.CAP_PROP_FRAME_COUNT)
    if rawFrameCount is None or rawFrameCount != rawFrameCount or rawFrameCount < 3:
      return None

    frameCount = int(rawFrameCount)
    sampleCount = min(BORDER_SCAN_SAMPLES, frameCount)
    sampleIndices = [
      round(index * (frameCount - 1) / max(1, sampleCount - 1))
      for index in range(sampleCount)
    ]
    sampledBounds: list[tuple[int, int, int, int]] = []
    frameHeight = frameWidth = 0

    try:
      for frameIndex in sampleIndices:
        if not capture.set(cv2Module.CAP_PROP_POS_FRAMES, frameIndex):
          return None
        isRead, frame = capture.read()
        if not isRead or frame is None:
          return None
        frameHeight, frameWidth = frame.shape[:2]
        sampledBounds.append(renderer.detectBlackBorders(frame))
    finally:
      # 先読みスレッドが必ず先頭から始められるように戻す
      capture.set(cv2Module.CAP_PROP_POS_FRAMES, 0)

    if not sampledBounds or frameHeight <= 0 or frameWidth <= 0:
      return None

    def persistentStart(values: list[int], size: int) -> int:
      minimumSize = max(2, round(size * renderer.LETTERBOX_MIN_FRACTION))
      tolerance = max(2, round(size * 0.01))
      if min(values) < minimumSize or max(values) - min(values) > tolerance:
        return 0
      return min(values)

    def persistentEnd(values: list[int], size: int) -> int:
      minimumSize = max(2, round(size * renderer.LETTERBOX_MIN_FRACTION))
      tolerance = max(2, round(size * 0.01))
      if size - max(values) < minimumSize or max(values) - min(values) > tolerance:
        return size
      return max(values)

    topValues = [bounds[0] for bounds in sampledBounds]
    bottomValues = [bounds[1] for bounds in sampledBounds]
    leftValues = [bounds[2] for bounds in sampledBounds]
    rightValues = [bounds[3] for bounds in sampledBounds]
    return (
      persistentStart(topValues, frameHeight),
      persistentEnd(bottomValues, frameHeight),
      persistentStart(leftValues, frameWidth),
      persistentEnd(rightValues, frameWidth),
    )

  def _preRenderVideo(self, capture) -> None:
    """動画を先頭から最後まで変換し，描画用の一時ファイルへ保存する."""
    terminalWidth, terminalHeight = self._terminalSize()
    frameStore = RenderedFrameStore()
    frameCount = 0
    try:
      while True:
        isRead, frame = capture.read()
        if not isRead or frame is None:
          break

        frameText, columns, rows, _, _ = self._renderFrameContent(
          frame, terminalWidth, terminalHeight
        )
        frameStore.append(frameText)
        if frameCount == 0:
          self._preRenderedLayout = (
            columns,
            rows,
            terminalWidth,
            terminalHeight,
          )
        frameCount += 1
        if self._isInteractiveStream() and frameCount % 30 == 0:
          print(f"\r事前生成中: {frameCount}フレーム", end="", file=sys.stderr, flush=True)
    except Exception:
      frameStore.close()
      self._preRenderedLayout = None
      raise

    if frameCount == 0 or self._preRenderedLayout is None:
      frameStore.close()
      raise PlaybackError("事前生成できるフレームがありません．")

    self._preRenderedFrames = frameStore
    if self._isInteractiveStream():
      print(f"\r事前生成完了: {frameCount}フレーム" + " " * 10, file=sys.stderr)

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

    # ffplay の起動遅延の分だけ先の位置から鳴らし，映像と頭出しを揃える
    startPosition = (
      self._mediaTime()
      + config.AUDIO_START_LATENCY * self._speed
      + self.options.audioOffset
    )
    self._audioPlayer.start(
      position=startPosition,
      speed=self._speed,
      volume=self._volume,
    )

  # -------------------------------------------------------------------------
  # メインループ
  # -------------------------------------------------------------------------

  def _runLoop(self, keyReader: KeyReader) -> None:
    """フレームの取得・描画・待機を繰り返す."""
    # 保存操作でも同じ入力元を使う
    self._keyReader = keyReader
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

      if self._preRenderedFrames is not None and self._terminalSizeChanged():
        # 事前生成した文字列は端末サイズに依存するため，サイズ変更後は
        # 現在位置から通常のフレーム読み込みへ安全に切り替える．
        self._switchToLiveRendering()

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

      if self._preRenderedFrames is not None:
        frameText = self._readPreparedFrame()
        if frameText is None:
          return
        self._lastRenderedMedia = frameTime
        self._drawPreparedFrame(frameText)
      else:
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
    if self._preRenderedFrames is not None:
      if self._nextFrameIndex >= len(self._preRenderedFrames):
        return False
      self._nextFrameIndex += 1
      return True
    if self._frameReader is not None:
      packet = self._frameReader.read()
      if packet is None:
        return False
      self._nextFrameIndex = packet[0] + 1
      return True
    if self._capture is None or not self._capture.grab():
      return False
    self._nextFrameIndex += 1
    return True

  def _readPreparedFrame(self) -> str | None:
    """事前生成済みフレームを1つ読み込む."""
    if self._preRenderedFrames is None:
      return None
    frameText = self._preRenderedFrames.read(self._nextFrameIndex)
    if frameText is None:
      return None
    self._nextFrameIndex += 1
    return frameText

  def _terminalSizeChanged(self) -> bool:
    """事前生成を開始した時点から端末サイズが変わったかどうかを返す."""
    if self._preRenderedLayout is None:
      return False
    return self._terminalSize() != self._preRenderedLayout[2:]

  def _switchToLiveRendering(self) -> bool:
    """端末サイズ変更時に，現在位置から通常描画へ切り替える."""
    if self._preRenderedFrames is None:
      return True

    import cv2

    newCapture = cv2.VideoCapture(self.videoPath)
    if not newCapture.isOpened():
      newCapture.release()
      # 再接続できないURLなどでは，古い生成結果を新しい端末の中央へ置く
      # ことで再生を止めずに継続する．
      terminalWidth, terminalHeight = self._terminalSize()
      columns, rows, _, _ = self._preRenderedLayout or (0, 0, 0, 0)
      self._preRenderedLayout = (columns, rows, terminalWidth, terminalHeight)
      self._lastSize = None
      return False

    newReader = FrameReader(newCapture)
    newReader.seek(cv2.CAP_PROP_POS_FRAMES, self._nextFrameIndex)

    oldCapture = self._capture
    oldStore = self._preRenderedFrames
    self._frameReader = newReader
    self._capture = newCapture
    self._preRenderedFrames = None
    self._preRenderedLayout = None
    self._lastSize = None
    oldStore.close()
    if oldCapture is not None and oldCapture is not newCapture:
      oldCapture.release()
    return True

  def _readFrame(self):
    """フレームを1つ読み込む．動画の終端では None を返す."""
    if self._frameReader is not None:
      packet = self._frameReader.read()
      if packet is None:
        return None
      frameIndex, frame = packet
      self._nextFrameIndex = frameIndex + 1
      return frame
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

    # Esc と Ctrl+C も終了として扱う（保存名の入力中は取り消しが優先される）
    if lowerKey == "q" or key == ESC or key == "\x03":
      return False

    if key == " ":
      self._togglePause()
      return True

    if lowerKey == "r":
      self._restart()
      return True

    if key in (KEY_LEFT, "h"):
      self._seekBy(-config.SEEK_STEP_SECONDS)
      return True

    if key in (KEY_RIGHT, "l"):
      self._seekBy(config.SEEK_STEP_SECONDS)
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

    if key == "0":
      self._changeVolume(config.VOLUME_STEP)
      return True

    if key == "9":
      self._changeVolume(-config.VOLUME_STEP)
      return True

    if lowerKey == "s":
      self._saveInteractively()
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
    if self._preRenderedFrames is None:
      import cv2

      if self._frameReader is not None:
        self._frameReader.seek(cv2.CAP_PROP_POS_FRAMES)
      elif self._capture is not None:
        self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
    self._nextFrameIndex = 0
    self._lastRenderedMedia = None
    self._mediaBase = 0.0
    self._startClock()
    self._syncAudio()

  def _seekBy(self, seconds: float) -> None:
    """現在位置から指定秒数だけ前後へ移動する."""
    target = max(0.0, self._mediaTime() + seconds)
    if self._duration > 0:
      target = min(target, self._duration)

    frameIndex = max(0, int(target * self._videoFps))
    if self._preRenderedFrames is not None:
      frameIndex = min(frameIndex, len(self._preRenderedFrames))
    else:
      import cv2

      if self._frameReader is not None:
        self._frameReader.seek(cv2.CAP_PROP_POS_FRAMES, frameIndex)
      elif self._capture is not None:
        self._capture.set(cv2.CAP_PROP_POS_FRAMES, frameIndex)

    self._nextFrameIndex = frameIndex
    self._lastRenderedMedia = None
    self._mediaBase = target
    self._startClock()
    self._syncAudio()

  def _toggleMute(self) -> None:
    """ミュートを切り替える．音声を使わない再生では何もしない."""
    if self._audioPlayer is None:
      return
    self._muted = not self._muted
    self._syncAudio()

  # -------------------------------------------------------------------------
  # 再生中の保存
  # -------------------------------------------------------------------------

  def _saveInteractively(self) -> None:
    """保存名の入力を受け付け，動画を手元へ保存して登録する."""
    if self.options.onSave is None or self._keyReader is None:
      return
    if not self._keyReader.enabled:
      # キー入力を扱えない環境では保存操作もできない
      return

    wasPlaying = not self._paused
    if wasPlaying:
      # 保存中は音声も止めておく
      self._togglePause()

    try:
      typedName = self._promptForName()
      if typedName is None:
        self._showMessage("保存を取り消しました．", waitForKey=False)
        return

      self._showMessage(f"「{typedName}」として保存しています．", waitForKey=False)
      try:
        resultMessage = self.options.onSave(typedName)
      except Exception as error:  # 保存の失敗で再生を止めない
        resultMessage = f"保存に失敗しました: {error}"
      self._showMessage(resultMessage, waitForKey=True)
    finally:
      if wasPlaying:
        self._togglePause()

  def _promptForName(self) -> str | None:
    """保存名を1文字ずつ受け取る．取り消した場合は None を返す."""
    typedName = ""
    while True:
      self._drawPromptLine(
        f"保存名: {typedName}_  [Enter]決定 [Esc]取消（英数字・_-.が使えます）"
      )
      key = self._keyReader.readKey(PROMPT_POLL_INTERVAL)
      if key is None:
        continue

      if key in ENTER_KEYS:
        return typedName or None
      if key == ESC:
        return None
      if key in BACKSPACE_KEYS:
        typedName = typedName[:-1]
        continue
      if len(key) == 1 and key.isprintable() and len(typedName) < MAX_INPUT_LENGTH:
        typedName += key

  def _showMessage(self, message: str, waitForKey: bool) -> None:
    """画面下部にメッセージを表示する."""
    suffix = "  [任意のキーで戻る]" if waitForKey else ""
    self._drawPromptLine(message + suffix)
    if not waitForKey or self._keyReader is None:
      return

    deadline = time.perf_counter() + MESSAGE_DISPLAY_SECONDS
    while time.perf_counter() < deadline:
      if self._keyReader.readKey(PROMPT_POLL_INTERVAL) is not None:
        return

  def _drawPromptLine(self, text: str) -> None:
    """ステータス行の位置へ，入力欄やメッセージを表示する."""
    if self._lastSize is None:
      return
    columns, rows, terminalWidth, terminalHeight = self._lastSize
    topOffset, _ = self._frameOffsets(
      columns, rows, terminalWidth, terminalHeight
    )
    body = truncateToWidth(sanitizeText(text), max(0, terminalWidth))
    self._write(
      f"{ESC}[{topOffset + rows + 1};1H{body}{RESET_ATTRIBUTES}{CLEAR_LINE}"
    )

  def _changeVolume(self, delta: int) -> None:
    """音量を変更する．音声を使わない再生では何もしない."""
    if self._audioPlayer is None:
      return

    newVolume = min(config.MAX_VOLUME, max(config.MIN_VOLUME, self._volume + delta))
    if newVolume == self._volume:
      return

    self._volume = newVolume
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
    frameText, columns, rows, terminalWidth, terminalHeight = self._renderFrameContent(frame)
    self._writeRenderedFrame(
      frameText, columns, rows, terminalWidth, terminalHeight
    )

  def _renderFrameContent(
    self,
    frame,
    terminalWidth: int | None = None,
    terminalHeight: int | None = None,
  ) -> tuple[str, int, int, int, int]:
    """フレームをクロップ・サイズ計算・文字列化する."""
    if self._letterboxBounds is None:
      self._letterboxBounds = (0, frame.shape[0], 0, frame.shape[1])
    top, bottom, left, right = self._letterboxBounds
    if top > 0 or bottom < frame.shape[0] or left > 0 or right < frame.shape[1]:
      # 映画由来の黒帯を除いてからサイズ計算し，映像部分を端末いっぱいに表示する
      frame = frame[top:bottom, left:right]

    frameHeight, frameWidth = frame.shape[:2]
    if terminalWidth is None or terminalHeight is None:
      terminalWidth, terminalHeight = self._terminalSize()
    columns, rows = renderer.computeSize(
      frameWidth,
      frameHeight,
      terminalWidth,
      terminalHeight,
      maxWidth=self.options.width,
      # ステータス行を出さない場合は，その1行も描画に使う
      reservedRows=config.STATUS_ROW_COUNT if self.options.showStatus else 0,
    )

    frameText = renderer.renderFrame(
      frame,
      self.options.mode,
      columns,
      rows,
      self.options.charset,
      self.options.brightness,
      self.options.contrast,
      self.options.color,
    )
    return frameText, columns, rows, terminalWidth, terminalHeight

  def _drawPreparedFrame(self, frameText: str) -> None:
    """事前生成済みの文字列を出力する."""
    if self._preRenderedLayout is None:
      return
    columns, rows, terminalWidth, terminalHeight = self._preRenderedLayout
    self._writeRenderedFrame(
      frameText, columns, rows, terminalWidth, terminalHeight
    )

  def _writeRenderedFrame(
    self,
    frameText: str,
    columns: int,
    rows: int,
    terminalWidth: int,
    terminalHeight: int,
  ) -> None:
    """文字列化済みフレームを端末へ描画する."""

    parts: list[str] = []
    currentSize = (columns, rows, terminalWidth, terminalHeight)
    if currentSize != self._lastSize:
      # サイズが変わったときだけ画面を消し，残像を防ぐ
      parts.append(CLEAR_SCREEN)
      self._lastSize = currentSize

    parts.append(CURSOR_HOME)
    topOffset, leftOffset = self._frameOffsets(
      columns, rows, terminalWidth, terminalHeight
    )
    if topOffset > 0:
      parts.append(f"{ESC}[{topOffset + 1};1H")
    linePrefix = " " * leftOffset
    parts.append(
      linePrefix + frameText.replace("\n", f"{CLEAR_LINE}\n{linePrefix}")
    )
    parts.append(CLEAR_LINE)

    if self.options.showStatus:
      parts.append(self._statusText(rows, terminalWidth, topOffset))

    self._write("".join(parts))

  def _frameOffsets(
    self,
    columns: int,
    rows: int,
    terminalWidth: int,
    terminalHeight: int,
  ) -> tuple[int, int]:
    """描画領域内で映像を中央へ置く余白（上，左）を返す."""
    availableRows = terminalHeight - (
      config.STATUS_ROW_COUNT if self.options.showStatus else 0
    )
    topOffset = max(0, (availableRows - rows) // 2)
    leftOffset = max(0, (terminalWidth - columns) // 2)
    return topOffset, leftOffset

  def _drawStatusOnly(self) -> None:
    """一時停止中に，ステータス行だけを更新する."""
    if not self.options.showStatus or self._lastSize is None:
      return
    columns, rows, terminalWidth, terminalHeight = self._lastSize
    topOffset, _ = self._frameOffsets(
      columns, rows, terminalWidth, terminalHeight
    )
    self._write(self._statusText(rows, terminalWidth, topOffset))

  def _statusText(self, rows: int, terminalWidth: int, rowOffset: int = 0) -> str:
    """画面下部に表示するステータス行を組み立てる."""
    state = "一時停止" if self._paused else "再生中"
    position = formatTime(self._mediaTime())
    total = formatTime(self._duration) if self._duration > 0 else "--:--"
    if self._audioPlayer is None:
      audioState = "-"
    elif self._muted:
      audioState = "消音"
    else:
      audioState = f"{self._volume}%"
    # 動画のタイトルは外部由来のため，制御文字を取り除いてから表示する
    title = sanitizeText(self.options.title or Path(self.videoPath).name)

    body = (
      f"{state} {title}  {position}/{total}  x{self._speed:.2f}  "
      f"{self.options.mode}  音声:{audioState}  {KEY_HELP}"
    )
    body = truncateToWidth(body, max(0, terminalWidth))

    # ステータス行は中央配置した描画領域のすぐ下へ表示する
    return f"{ESC}[{rowOffset + rows + 1};1H{DIM}{body}{RESET_ATTRIBUTES}{CLEAR_LINE}"

  def _write(self, text: str) -> None:
    """出力先へ書き込む．端末が閉じられている場合は再生を終了させる."""
    try:
      self.stream.write(text)
      self.stream.flush()
    except (BrokenPipeError, ValueError):
      raise PlaybackError("出力先へ書き込めなくなったため再生を終了します．")
