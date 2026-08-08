"""登録済み動画の設定を，対話的に編集する画面のモジュール."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, TextIO

from . import menu, terminal
from .keyboard import KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_UP, KeyReader
from .registry import Registry, VideoEntry
from .textwidth import displayWidth, padToWidth, sanitizeText, truncateToWidth

# 見出し・区切り線2本・操作説明で，本文以外に4行を使う
CHROME_ROWS = 4

# 未設定に戻せない項目は，この既定値へ戻す
DEFAULT_ENTRY = VideoEntry(name="", path="")

# URLを登録した場合にだけ意味を持つ項目
REMOTE_ONLY_KEYS = frozenset(
  {"quality", "cache", "cookiesFromBrowser", "cookiesFile", "playerClient"}
)

# 空欄にできる（未設定を選べる）項目
NULLABLE_KEYS = frozenset(
  {"width", "fps", "charset", "quality", "cookiesFromBrowser", "cookiesFile", "playerClient"}
)


@dataclass
class EditorState:
  """編集画面の選択状態を保持するデータクラス."""

  itemIndex: int = 0
  scrollOffset: int = 0
  message: str = ""
  editing: bool = False
  editBuffer: str = ""


class EntryEditor:
  """登録済み動画の設定を1画面で編集するクラス."""

  def __init__(self, name: str, stream: TextIO | None = None) -> None:
    self.name = name
    self.stream = stream or sys.stdout
    self.state = EditorState()

    self.registry = Registry()
    self.entry = self.registry.get(name)
    self.items = self._visibleItems()
    self._scrollIndicator = ""

  def _visibleItems(self) -> list[menu.SettingItem]:
    """この登録内容で意味のある項目だけを並べる."""
    return [
      item
      for item in menu.SETTING_ITEMS
      if self.entry.isRemote or item.key not in REMOTE_ONLY_KEYS
    ]

  @property
  def currentItem(self) -> menu.SettingItem | None:
    """選択中の項目を返す."""
    if not self.items:
      return None
    return self.items[self.state.itemIndex % len(self.items)]

  def currentValue(self, item: menu.SettingItem) -> Any:
    """登録内容から，その項目の現在値を取り出す."""
    return getattr(self.entry, item.key, None)

  # ---------------------------------------------------------------------
  # 表示
  # ---------------------------------------------------------------------

  def bodyLines(self) -> list[str]:
    """項目の一覧を組み立てる."""
    labelWidth = max(displayWidth(item.label) for item in self.items)
    location = sanitizeText(self.entry.path)

    lines = [
      f"{terminal.DIM}{'URL' if self.entry.isRemote else 'ファイル'}: {location}"
      f"{terminal.RESET_ATTRIBUTES}",
      "← → で変更（その場で保存されます），Enter で直接入力，d で既定へ戻します．",
      "",
    ]
    for index, item in enumerate(self.items):
      marker = "▸" if index == self.state.itemIndex else " "
      value = self.currentValue(item)
      row = (
        f"{marker} {padToWidth(item.label, labelWidth)}  "
        f"{padToWidth(menu.formatValue(value), 12)}"
      )
      explanation = menu.describeValue(item, value)
      if index == self.state.itemIndex:
        lines.append(f"{terminal.BOLD}{row}{terminal.RESET_ATTRIBUTES}  {explanation}")
      else:
        lines.append(f"{row}  {terminal.DIM}{explanation}{terminal.RESET_ATTRIBUTES}")

    return lines

  def footerLine(self, width: int) -> str:
    """画面下部の操作説明を組み立てる."""
    if self.state.editing:
      item = self.currentItem
      label = item.label if item else ""
      return truncateToWidth(
        f"{label}: {self.state.editBuffer}_  "
        f"[Enter]決定 [↑↓]確定して移動 [Esc]取消",
        width,
      )

    if self.state.message:
      return truncateToWidth(self.state.message, width)

    position = f" {self._scrollIndicator}" if self._scrollIndicator else ""
    return truncateToWidth(
      f"[↑↓]移動 [←→]変更 [Enter]入力 [d]既定へ [q/Esc]終了{position}", width
    )

  def renderLines(self, width: int, height: int) -> list[str]:
    """画面全体の行を組み立てる."""
    bodyHeight = max(1, height - CHROME_ROWS)
    allLines = self.bodyLines()

    # 選択中の項目が画面の外に出ないよう表示範囲をずらす
    headerLines = 3
    selectedLine = headerLines + self.state.itemIndex
    if selectedLine < self.state.scrollOffset:
      self.state.scrollOffset = selectedLine
    elif selectedLine >= self.state.scrollOffset + bodyHeight:
      self.state.scrollOffset = selectedLine - bodyHeight + 1
    maxOffset = max(0, len(allLines) - bodyHeight)
    self.state.scrollOffset = max(0, min(self.state.scrollOffset, maxOffset))

    body = allLines[self.state.scrollOffset : self.state.scrollOffset + bodyHeight]
    self._scrollIndicator = (
      f"[{self.state.scrollOffset + 1}-{self.state.scrollOffset + len(body)}"
      f"/{len(allLines)}]"
      if len(allLines) > bodyHeight
      else ""
    )
    body += [""] * (bodyHeight - len(body))

    return [
      truncateToWidth(
        f"{terminal.BOLD}「{self.name}」の設定{terminal.RESET_ATTRIBUTES}"
        f"  {terminal.DIM}変更はすぐ保存されます{terminal.RESET_ATTRIBUTES}",
        width,
      ),
      terminal.RESET_ATTRIBUTES + "─" * width,
      *[truncateToWidth(line, width) for line in body],
      "─" * width,
      self.footerLine(width),
    ]

  def draw(self) -> None:
    """画面を描き直す."""
    width, height = terminal.terminalSize()
    lines = self.renderLines(width, height)
    body = f"{terminal.CLEAR_LINE}\n".join(lines)
    self.stream.write(f"{terminal.CURSOR_HOME}{body}{terminal.CLEAR_LINE}")
    self.stream.flush()

  # ---------------------------------------------------------------------
  # 操作
  # ---------------------------------------------------------------------

  def handleKey(self, key: str) -> bool:
    """キー入力を処理する．終了する場合は偽を返す."""
    if self.state.editing:
      return self._handleEditKey(key)

    if key in ("q", "Q") or key == terminal.ESC:
      return False
    if key in ("j", KEY_DOWN):
      self._moveItem(1)
      return True
    if key in ("k", KEY_UP):
      self._moveItem(-1)
      return True
    if key in ("h", KEY_LEFT):
      self._adjustSelected(-1)
      return True
    if key in ("l", KEY_RIGHT):
      self._adjustSelected(1)
      return True
    if key == "d":
      self._resetSelected()
      return True
    if key in menu.ENTER_KEYS:
      self._activateItem()
      return True

    return True

  def _handleEditKey(self, key: str) -> bool:
    """値の入力中のキーを処理する."""
    if key in menu.ARROW_KEYS:
      # 入力をそのまま確定し，矢印キー本来の移動・変更へ進む
      self._commitEdit()
      return self.handleKey(key)

    if key == terminal.ESC:
      self.state.editing = False
      self.state.editBuffer = ""
      self.state.message = "変更を取り消しました．"
      return True

    if key in menu.ENTER_KEYS:
      self._commitEdit()
      return True

    if key in menu.BACKSPACE_KEYS:
      self.state.editBuffer = self.state.editBuffer[:-1]
      return True

    if (
      len(key) == 1
      and key.isprintable()
      and len(self.state.editBuffer) < menu.MAX_INPUT_LENGTH
    ):
      self.state.editBuffer += key
    return True

  def _moveItem(self, delta: int) -> None:
    """項目の選択を移動する."""
    if not self.items:
      return
    self.state.itemIndex = (self.state.itemIndex + delta) % len(self.items)

  def _adjustSelected(self, direction: int) -> None:
    """選択中の項目を1段階変更する."""
    item = self.currentItem
    if item is None:
      return

    newValue = menu.adjustValue(item, self.currentValue(item), direction)
    if newValue is None and item.key not in NULLABLE_KEYS:
      # 空欄にできない項目は，未設定を飛ばして次の値へ進める
      newValue = menu.adjustValue(item, newValue, direction)
    self._storeValue(item, newValue)

  def _resetSelected(self) -> None:
    """選択中の項目を，登録時の既定値へ戻す."""
    item = self.currentItem
    if item is None:
      return
    self._storeValue(item, getattr(DEFAULT_ENTRY, item.key, None))

  def _activateItem(self) -> None:
    """選択肢は次の値へ進め，数値・文字列は入力欄を開く."""
    item = self.currentItem
    if item is None:
      return

    if item.kind in ("choice", "bool"):
      self._adjustSelected(1)
      return

    currentValue = self.currentValue(item)
    self.state.editing = True
    self.state.editBuffer = "" if currentValue is None else str(currentValue)
    self.state.message = ""

  def _commitEdit(self) -> None:
    """入力された値を保存する."""
    item = self.currentItem
    self.state.editing = False
    if item is None:
      return

    try:
      value = menu.parseTextValue(item, self.state.editBuffer)
    except ValueError:
      self.state.message = f"「{self.state.editBuffer}」は数値として読み取れません．"
      self.state.editBuffer = ""
      return

    self.state.editBuffer = ""
    if value is None and item.key not in NULLABLE_KEYS:
      value = getattr(DEFAULT_ENTRY, item.key, None)
    self._storeValue(item, value)

  def _storeValue(self, item: menu.SettingItem, value: Any) -> None:
    """変更を登録内容へ保存する."""
    if value == self.currentValue(item):
      return

    try:
      self.entry = self.registry.update(self.name, {item.key: value})
    except Exception as error:  # 保存に失敗しても編集は続けられるようにする
      self.state.message = f"保存できませんでした: {error}"
      return

    self.state.message = f"{item.label} を {menu.formatValue(value)} にしました．"

  # ---------------------------------------------------------------------
  # 実行
  # ---------------------------------------------------------------------

  def run(self) -> None:
    """編集画面を表示し，キー操作を受け付ける."""
    terminal.enterFullScreen(self.stream)
    try:
      with KeyReader() as keyReader:
        self.draw()
        if not keyReader.enabled:
          # キー入力を扱えない環境では，内容を1度表示して終える
          return

        while True:
          key = keyReader.readKey(menu.POLL_INTERVAL)
          if key is None:
            continue
          if not self.handleKey(key):
            return
          self.draw()
    finally:
      terminal.leaveFullScreen(self.stream)


def editEntry(name: str, stream: TextIO | None = None) -> None:
  """登録名を指定して編集画面を開く."""
  EntryEditor(name, stream).run()
