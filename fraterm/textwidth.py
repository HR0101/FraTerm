"""全角文字を考慮した表示幅を扱うモジュール."""

from __future__ import annotations

import re
import unicodedata

# 表示幅が2文字分になる East Asian Width の区分
WIDE_CATEGORIES = ("W", "F")

# CSIシーケンス（ESC [ ... 終端）と，2文字のエスケープシーケンス
ANSI_SEQUENCE_PATTERN = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-Z\\-_]")


def charWidth(character: str) -> int:
  """1文字の表示幅（1または2）を返す."""
  return 2 if unicodedata.east_asian_width(character) in WIDE_CATEGORIES else 1


def displayWidth(text: str) -> int:
  """文字列全体の表示幅を返す（ANSIエスケープは幅に数えない）."""
  return sum(charWidth(character) for character in stripAnsi(text))


def stripAnsi(text: str) -> str:
  """ANSIエスケープシーケンスを取り除いた文字列を返す."""
  return ANSI_SEQUENCE_PATTERN.sub("", text)


def truncateToWidth(text: str, maxWidth: int) -> str:
  """表示幅が maxWidth を超えないように文字列を切り詰める.

  文字装飾のエスケープシーケンスは幅に数えず，そのまま残す.
  """
  if maxWidth <= 0:
    return ""

  currentWidth = 0
  parts: list[str] = []
  index = 0
  length = len(text)

  while index < length:
    match = ANSI_SEQUENCE_PATTERN.match(text, index)
    if match is not None:
      # 装飾は幅を持たないため，そのまま通す
      parts.append(match.group())
      index = match.end()
      continue

    character = text[index]
    width = charWidth(character)
    if currentWidth + width > maxWidth:
      break
    parts.append(character)
    currentWidth += width
    index += 1

  return "".join(parts)


def sanitizeText(text: str) -> str:
  """端末制御に使われる文字を取り除く.

  動画のタイトルやファイル名など，外部から来た文字列をそのまま出力すると，
  エスケープシーケンスによって表示を書き換えられてしまうため取り除く.
  """
  # ESC単体を落とすだけでは「[2J」のような残骸が出るため，まとめて取り除く
  withoutSequences = ANSI_SEQUENCE_PATTERN.sub("", text)
  return "".join(
    character
    for character in withoutSequences
    if character == " " or character.isprintable()
  )


def padToWidth(text: str, width: int) -> str:
  """表示幅が width になるように右側へ空白を追加する."""
  padding = width - displayWidth(text)
  return text + " " * padding if padding > 0 else text
