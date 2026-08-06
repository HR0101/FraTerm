"""再生中のキー入力を受け取るモジュール（OS差分をここに閉じ込める）."""

from __future__ import annotations

import os
import sys
import time

# 端末をノンブロッキングで読むためのモジュールはOSによって異なる
try:  # POSIX（macOS / Linux）
  import select
  import termios
  import tty

  IS_POSIX = True
except ImportError:  # Windows
  IS_POSIX = False

try:  # Windows
  import msvcrt

  HAS_MSVCRT = True
except ImportError:
  HAS_MSVCRT = False

# キー入力を1回読み出す際の最大バイト数（エスケープシーケンス対策）
READ_CHUNK_SIZE = 8

# Windowsでキー入力を待つ際のポーリング間隔（秒）
WINDOWS_POLL_INTERVAL = 0.01

ESC = "\x1b"


class KeyReader:
  """ターミナルを1文字入力モードにして，押されたキーを取得するクラス."""

  def __init__(self) -> None:
    self._fileDescriptor: int | None = None
    self._originalSettings = None
    self._enabled = False

  # ---------------------------------------------------------------------
  # コンテキストマネージャ
  # ---------------------------------------------------------------------

  def __enter__(self) -> "KeyReader":
    self.open()
    return self

  def __exit__(self, *exceptionInfo) -> bool:
    self.close()
    return False

  @property
  def enabled(self) -> bool:
    """キー入力を受け付けられる状態かどうかを返す."""
    return self._enabled

  def open(self) -> None:
    """端末を1文字入力モードへ切り替える．対応できない場合は無効のままにする."""
    if not sys.stdin.isatty():
      # パイプ経由の実行などではキー入力を扱わない
      self._enabled = False
      return

    if IS_POSIX:
      try:
        self._fileDescriptor = sys.stdin.fileno()
        self._originalSettings = termios.tcgetattr(self._fileDescriptor)
        # cbreak なら Ctrl+C は従来どおり割り込みとして扱われる
        tty.setcbreak(self._fileDescriptor)
        self._enabled = True
      except (termios.error, ValueError, OSError):
        self._enabled = False
      return

    self._enabled = HAS_MSVCRT

  def close(self) -> None:
    """端末の設定を元に戻す."""
    if IS_POSIX and self._originalSettings is not None and self._fileDescriptor is not None:
      try:
        termios.tcsetattr(
          self._fileDescriptor, termios.TCSADRAIN, self._originalSettings
        )
      except (termios.error, ValueError, OSError):
        pass
    self._originalSettings = None
    self._fileDescriptor = None
    self._enabled = False

  # ---------------------------------------------------------------------
  # 入力
  # ---------------------------------------------------------------------

  def readKey(self, timeout: float = 0.0) -> str | None:
    """timeout秒だけキー入力を待ち，押されたキーを返す．無ければ None を返す.

    キー入力が無効な環境では，指定時間だけ待機してから None を返す.
    """
    waitSeconds = max(0.0, timeout)

    if not self._enabled:
      if waitSeconds > 0.0:
        time.sleep(waitSeconds)
      return None

    if IS_POSIX:
      return self._readKeyPosix(waitSeconds)
    return self._readKeyWindows(waitSeconds)

  def _readKeyPosix(self, waitSeconds: float) -> str | None:
    """POSIX環境でキー入力を1つ読み出す."""
    if self._fileDescriptor is None:
      return None

    try:
      readable, _, _ = select.select([self._fileDescriptor], [], [], waitSeconds)
    except (OSError, ValueError):
      return None

    if not readable:
      return None

    try:
      data = os.read(self._fileDescriptor, READ_CHUNK_SIZE)
    except OSError:
      return None

    return self._decode(data.decode("utf-8", errors="ignore"))

  def _readKeyWindows(self, waitSeconds: float) -> str | None:
    """Windows環境でキー入力を1つ読み出す."""
    deadline = time.perf_counter() + waitSeconds
    while True:
      if msvcrt.kbhit():
        character = msvcrt.getwch()
        return self._decode(character)
      if time.perf_counter() >= deadline:
        return None
      time.sleep(WINDOWS_POLL_INTERVAL)

  @staticmethod
  def _decode(rawInput: str) -> str | None:
    """読み出した文字列から，処理対象とする1文字を取り出す."""
    if not rawInput:
      return None
    # 矢印キーなどのエスケープシーケンスは無視する
    if rawInput.startswith(ESC):
      return None
    return rawInput[0]
