"""動画フレームをバックグラウンドで先読みする小さなデコーダ."""

from __future__ import annotations

import queue
import threading
from typing import Any


# 先読みしすぎるとメモリを圧迫し，少なすぎると一時的なデコード遅延を吸収できない．
DEFAULT_BUFFER_SIZE = 4
READ_TIMEOUT = 0.05
JOIN_TIMEOUT = 0.5


class FrameReader:
  """VideoCaptureを専用スレッドで読み，描画側へ有限個のフレームを渡す."""

  def __init__(self, capture: Any, bufferSize: int = DEFAULT_BUFFER_SIZE) -> None:
    if bufferSize < 1:
      raise ValueError("bufferSize must be positive")

    self._capture = capture
    self._frames: queue.Queue[tuple[int, int, Any | None]] = queue.Queue(bufferSize)
    self._stopEvent = threading.Event()
    self._stateLock = threading.Lock()
    self._generation = 0
    self._nextFrameIndex = 0
    self._eofGeneration: int | None = None
    self._thread = threading.Thread(
      target=self._run,
      name="fraterm-frame-reader",
      daemon=True,
    )
    self._thread.start()

  def _run(self) -> None:
    """動画から読み続け，キューが満杯なら先読みを一時停止する."""
    while not self._stopEvent.is_set():
      with self._stateLock:
        generation = self._generation
        frameIndex = self._nextFrameIndex
        try:
          isRead, frame = self._capture.read()
        except Exception:
          isRead, frame = False, None

        if isRead and frame is not None:
          self._nextFrameIndex += 1
          packet = (generation, frameIndex, frame)
        else:
          self._eofGeneration = generation
          packet = (generation, frameIndex, None)

      if not self._put(packet):
        return
      if packet[2] is None:
        return

  def _put(self, packet: tuple[int, int, Any | None]) -> bool:
    """世代が変わった古いパケットを捨てながらキューへ追加する."""
    while not self._stopEvent.is_set():
      with self._stateLock:
        if packet[0] != self._generation:
          return True
      try:
        self._frames.put(packet, timeout=READ_TIMEOUT)
        return True
      except queue.Full:
        continue
    return False

  def read(self) -> tuple[int, Any] | None:
    """次のフレームを返す．終端または終了後はNoneを返す."""
    while not self._stopEvent.is_set():
      with self._stateLock:
        generation = self._generation
        reachedEnd = self._eofGeneration == generation

      try:
        packetGeneration, frameIndex, frame = self._frames.get(timeout=READ_TIMEOUT)
      except queue.Empty:
        if reachedEnd:
          return None
        continue

      if packetGeneration != generation:
        continue
      if frame is None:
        return None
      return frameIndex, frame
    return None

  def discard(self) -> bool:
    """次のフレームを読み捨てる．終端ならFalseを返す."""
    return self.read() is not None

  def seek(self, positionProperty: int, frameIndex: int = 0) -> None:
    """指定フレームへ移動し，移動前に先読みしたフレームを無効にする."""
    with self._stateLock:
      self._generation += 1
      self._nextFrameIndex = max(0, frameIndex)
      self._eofGeneration = None
      self._capture.set(positionProperty, self._nextFrameIndex)

      while True:
        try:
          self._frames.get_nowait()
        except queue.Empty:
          break

  def close(self) -> None:
    """先読みスレッドを停止する．VideoCaptureの解放は呼び出し側が行う."""
    self._stopEvent.set()
    self._thread.join(JOIN_TIMEOUT)
