"""端末制御のエスケープシーケンスをまとめたモジュール."""

from __future__ import annotations

import shutil
from typing import TextIO

from . import config

ESC = "\x1b"
ENTER_ALT_SCREEN = f"{ESC}[?1049h"
LEAVE_ALT_SCREEN = f"{ESC}[?1049l"
HIDE_CURSOR = f"{ESC}[?25l"
SHOW_CURSOR = f"{ESC}[?25h"
CLEAR_SCREEN = f"{ESC}[2J"
CURSOR_HOME = f"{ESC}[H"
CLEAR_LINE = f"{ESC}[K"
RESET_ATTRIBUTES = f"{ESC}[0m"

# 文字装飾
DIM = f"{ESC}[2m"
BOLD = f"{ESC}[1m"
REVERSE = f"{ESC}[7m"
UNDERLINE = f"{ESC}[4m"


def moveTo(row: int, column: int = 1) -> str:
  """カーソルを指定位置（1始まり）へ動かすシーケンスを返す."""
  return f"{ESC}[{max(1, row)};{max(1, column)}H"


def terminalSize() -> tuple[int, int]:
  """ターミナルの桁数と行数を返す."""
  size = shutil.get_terminal_size(config.FALLBACK_TERMINAL_SIZE)
  return size.columns, size.lines


def isInteractive(stream: TextIO) -> bool:
  """出力先がターミナルかどうかを返す."""
  try:
    return bool(stream.isatty())
  except (AttributeError, ValueError):
    return False


def enterFullScreen(stream: TextIO) -> None:
  """代替画面へ切り替え，カーソルを隠す."""
  if not isInteractive(stream):
    return
  stream.write(ENTER_ALT_SCREEN + HIDE_CURSOR + CLEAR_SCREEN)
  stream.flush()


def leaveFullScreen(stream: TextIO) -> None:
  """カーソルと画面の状態を元へ戻す."""
  try:
    if isInteractive(stream):
      stream.write(RESET_ATTRIBUTES + SHOW_CURSOR + LEAVE_ALT_SCREEN)
    else:
      stream.write(RESET_ATTRIBUTES + "\n")
    stream.flush()
  except (ValueError, OSError):
    pass
