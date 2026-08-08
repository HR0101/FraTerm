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

# キー入力を1回読み出す際の最大バイト数．キーリピートでも取りこぼさない大きさにする
READ_CHUNK_SIZE = 64

# 未完のエスケープシーケンスをEscキーとして確定するまでの待ち時間（秒）
PARTIAL_TIMEOUT = 0.05

# Windowsでキー入力を待つ際のポーリング間隔（秒）
WINDOWS_POLL_INTERVAL = 0.01

ESC = "\x1b"

# 矢印キー．エスケープシーケンスのまま返すため，文字入力とは区別できる
KEY_UP = f"{ESC}[A"
KEY_DOWN = f"{ESC}[B"
KEY_RIGHT = f"{ESC}[C"
KEY_LEFT = f"{ESC}[D"

# 認識するシーケンスの終端文字と，対応するキー
ARROW_KEYS = {"A": KEY_UP, "B": KEY_DOWN, "C": KEY_RIGHT, "D": KEY_LEFT}


class KeyReader:
  """ターミナルを1文字入力モードにして，押されたキーを取得するクラス."""

  def __init__(self) -> None:
    self._fileDescriptor: int | None = None
    self._originalSettings = None
    self._enabled = False
    # 一度に複数文字が届いた場合に，残りを次回以降へ回すための待ち行列
    self._pendingKeys: list[str] = []
    # 読み取りの境界で分断されたエスケープシーケンスの断片
    self._partialInput = ""
    self._partialSince = 0.0

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
    # 前回の読み取りで余った入力があれば，そちらを先に返す
    if self._pendingKeys:
      return self._pendingKeys.pop(0)

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
      return self._flushPartialInput()

    try:
      data = os.read(self._fileDescriptor, READ_CHUNK_SIZE)
    except OSError:
      return None

    return self._takeFirst(data.decode("utf-8", errors="ignore"))

  def _readKeyWindows(self, waitSeconds: float) -> str | None:
    """Windows環境でキー入力を1つ読み出す."""
    deadline = time.perf_counter() + waitSeconds
    while True:
      if msvcrt.kbhit():
        character = msvcrt.getwch()
        return self._takeFirst(character)
      if time.perf_counter() >= deadline:
        return self._flushPartialInput()
      time.sleep(WINDOWS_POLL_INTERVAL)

  def _takeFirst(self, rawInput: str) -> str | None:
    """読み出した文字列を分解し，先頭のキーを返す（残りは次回へ回す）."""
    # 前回の読み取りで途中だったシーケンスの続きとして扱う
    keys, remainder = self._tokenize(self._partialInput + rawInput)
    self._partialInput = remainder
    self._partialSince = time.perf_counter() if remainder else 0.0

    if not keys:
      return None

    self._pendingKeys.extend(keys[1:])
    return keys[0]

  def _flushPartialInput(self) -> str | None:
    """続きが届かなかった未完の入力を，Escキーとして確定する."""
    if not self._partialInput:
      return None
    if time.perf_counter() - self._partialSince < PARTIAL_TIMEOUT:
      return None

    self._partialInput = ""
    self._partialSince = 0.0
    return ESC

  @staticmethod
  def _tokenize(rawInput: str) -> tuple[list[str], str]:
    """入力文字列を1つずつのキーへ分解し，未完の部分と合わせて返す.

    文字入力では複数文字がまとめて届くため，すべてを取り出す必要がある.
    エスケープシーケンスは読み取りの境界で分断されることがあるので，
    途中で切れた分は次回の入力と連結できるよう残りとして返す.
    """
    keys: list[str] = []
    index = 0
    length = len(rawInput)

    while index < length:
      character = rawInput[index]
      if character != ESC:
        keys.append(character)
        index += 1
        continue

      # ESC単独か，続きがまだ届いていないか判断できないため保留する
      if index + 1 >= length:
        return keys, rawInput[index:]

      # CSI（ESC [ ... 終端文字）などのシーケンス
      if rawInput[index + 1] in ("[", "O"):
        end = index + 2
        while end < length and not ("@" <= rawInput[end] <= "~"):
          end += 1

        if end >= length:
          # 終端文字がまだ届いていないので，次回へ持ち越す
          return keys, rawInput[index:]

        # 矢印キーだけは操作に使うため，シーケンスのまま取り出す
        arrowKey = ARROW_KEYS.get(rawInput[end]) if end - index == 2 else None
        if arrowKey is not None:
          keys.append(arrowKey)
        index = end + 1
        continue

      keys.append(ESC)
      index += 1

    return keys, ""
