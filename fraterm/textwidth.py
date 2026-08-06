"""全角文字を考慮した表示幅を扱うモジュール."""

from __future__ import annotations

import unicodedata

# 表示幅が2文字分になる East Asian Width の区分
WIDE_CATEGORIES = ("W", "F")


def charWidth(character: str) -> int:
  """1文字の表示幅（1または2）を返す."""
  return 2 if unicodedata.east_asian_width(character) in WIDE_CATEGORIES else 1


def displayWidth(text: str) -> int:
  """文字列全体の表示幅を返す."""
  return sum(charWidth(character) for character in text)


def truncateToWidth(text: str, maxWidth: int) -> str:
  """表示幅が maxWidth を超えないように文字列を切り詰める."""
  if maxWidth <= 0:
    return ""

  currentWidth = 0
  characters: list[str] = []
  for character in text:
    width = charWidth(character)
    if currentWidth + width > maxWidth:
      break
    characters.append(character)
    currentWidth += width
  return "".join(characters)


def padToWidth(text: str, width: int) -> str:
  """表示幅が width になるように右側へ空白を追加する."""
  padding = width - displayWidth(text)
  return text + " " * padding if padding > 0 else text
