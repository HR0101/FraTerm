"""登録内容の対話編集に関するテスト."""

from __future__ import annotations

import io

import pytest

from fraterm import cli, config, editor, menu
from fraterm.errors import NameNotFoundError
from fraterm.keyboard import KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_UP
from fraterm.registry import Registry
from fraterm.textwidth import displayWidth, stripAnsi

SAMPLE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.fixture
def registeredEditor(dummyVideo):
  """ローカル動画を登録し，その編集画面を返す."""
  cli.main(["add", "sample", str(dummyVideo)])
  return editor.EntryEditor("sample", stream=io.StringIO())


def indexOf(screen: editor.EntryEditor, key: str) -> int:
  """項目の並びから，指定した設定の位置を返す."""
  return [item.key for item in screen.items].index(key)


def test_editorRequiresExistingEntry():
  """未登録の名前で開こうとするとエラーになることを確認する."""
  with pytest.raises(NameNotFoundError):
    editor.EntryEditor("unknown", stream=io.StringIO())


def test_screenRendersWithinWidth(registeredEditor):
  """各行が画面幅に収まることを確認する."""
  width = 70
  for line in registeredEditor.renderLines(width, 20):
    assert displayWidth(line) <= width, stripAnsi(line)


def test_screenHeightMatchesTerminal(registeredEditor):
  """描画する行数がターミナルの高さと一致することを確認する."""
  for height in (12, 20, 40):
    assert len(registeredEditor.renderLines(80, height)) == height


def test_localEntryHidesUrlOnlyItems(registeredEditor):
  """ローカル動画では，URL専用の項目を表示しないことを確認する."""
  shownKeys = {item.key for item in registeredEditor.items}
  assert not (shownKeys & editor.REMOTE_ONLY_KEYS)


def test_urlEntryShowsUrlOnlyItems():
  """URL登録では，画質やCookieの項目も表示されることを確認する."""
  cli.main(["add", "opening", SAMPLE_URL])
  screen = editor.EntryEditor("opening", stream=io.StringIO())

  shownKeys = {item.key for item in screen.items}
  assert "quality" in shownKeys
  assert "cookiesFromBrowser" in shownKeys


def test_arrowKeysChangeAndSaveImmediately(registeredEditor):
  """左右キーの変更が，その場で登録内容へ保存されることを確認する."""
  registeredEditor.state.itemIndex = indexOf(registeredEditor, "mode")

  registeredEditor.handleKey(KEY_RIGHT)
  assert Registry().get("sample").mode == config.AVAILABLE_MODES[1]

  registeredEditor.handleKey(KEY_LEFT)
  assert Registry().get("sample").mode == config.AVAILABLE_MODES[0]


def test_requiredItemSkipsUnsetValue(registeredEditor):
  """空にできない項目では，未設定を飛ばして次の値へ進むことを確認する."""
  registeredEditor.state.itemIndex = indexOf(registeredEditor, "mode")

  # 先頭から左へ戻しても未設定にはならない
  for _ in range(len(config.AVAILABLE_MODES) + 2):
    registeredEditor.handleKey(KEY_LEFT)
    assert Registry().get("sample").mode in config.AVAILABLE_MODES


def test_nullableItemCanBecomeUnset(registeredEditor):
  """空にできる項目は未設定へ戻せることを確認する."""
  cli.main(["edit", "sample", "--width", "80"])
  screen = editor.EntryEditor("sample", stream=io.StringIO())
  screen.state.itemIndex = indexOf(screen, "charset")

  screen.handleKey(KEY_RIGHT)
  assert Registry().get("sample").charset is not None

  screen.handleKey(KEY_LEFT)
  assert Registry().get("sample").charset is None


def test_numericItemStepsWithArrowKeys(registeredEditor):
  """数値の項目が刻み幅どおりに増減することを確認する."""
  registeredEditor.state.itemIndex = indexOf(registeredEditor, "volume")
  volumeItem = next(item for item in registeredEditor.items if item.key == "volume")

  registeredEditor.handleKey(KEY_LEFT)
  assert Registry().get("sample").volume == config.DEFAULT_VOLUME - volumeItem.step


def test_typedValueIsSaved(registeredEditor):
  """入力欄から値を打ち込んで保存できることを確認する."""
  registeredEditor.state.itemIndex = indexOf(registeredEditor, "width")

  registeredEditor.handleKey("\r")
  assert registeredEditor.state.editing is True
  for character in "120":
    registeredEditor.handleKey(character)
  registeredEditor.handleKey("\r")

  assert Registry().get("sample").width == 120


def test_typedValueCanBeCancelled(registeredEditor):
  """入力中の Esc で編集を取り消せることを確認する."""
  registeredEditor.state.itemIndex = indexOf(registeredEditor, "width")

  registeredEditor.handleKey("\r")
  registeredEditor.handleKey("9")
  assert registeredEditor.handleKey("\x1b") is True  # 画面は閉じない

  assert registeredEditor.state.editing is False
  assert Registry().get("sample").width is None


def test_invalidNumberIsReported(registeredEditor):
  """数値でない入力を保存せず，メッセージで知らせることを確認する."""
  registeredEditor.state.itemIndex = indexOf(registeredEditor, "width")

  registeredEditor.handleKey("\r")
  for character in "abc":
    registeredEditor.handleKey(character)
  registeredEditor.handleKey("\r")

  assert Registry().get("sample").width is None
  assert "読み取れません" in registeredEditor.state.message


def test_resetKeyRestoresDefault(registeredEditor):
  """d キーで登録時の既定値へ戻せることを確認する."""
  cli.main(["edit", "sample", "--mode", "color", "--volume", "40"])
  screen = editor.EntryEditor("sample", stream=io.StringIO())

  screen.state.itemIndex = indexOf(screen, "mode")
  screen.handleKey("d")
  assert Registry().get("sample").mode == config.DEFAULT_MODE

  screen.state.itemIndex = indexOf(screen, "volume")
  screen.handleKey("d")
  assert Registry().get("sample").volume == config.DEFAULT_VOLUME


@pytest.mark.parametrize("key", ["q", "Q", "\x1b"])
def test_quitKeysCloseEditor(registeredEditor, key):
  """q と Esc で編集画面を閉じられることを確認する."""
  assert registeredEditor.handleKey(key) is False


def test_selectionMovesAndStaysVisible(registeredEditor):
  """選択が移動し，画面に収まらない場合もその行が表示されることを確認する."""
  for _ in range(len(registeredEditor.items) - 1):
    registeredEditor.handleKey(KEY_DOWN)

  lines = [stripAnsi(line) for line in registeredEditor.renderLines(76, 14)]
  lastItem = registeredEditor.items[-1]
  assert any(lastItem.label in line and "▸" in line for line in lines)

  registeredEditor.handleKey(KEY_UP)
  assert registeredEditor.state.itemIndex == len(registeredEditor.items) - 2


def test_valueDescriptionIsShown(registeredEditor):
  """選んだ値の説明が画面へ出ることを確認する."""
  registeredEditor.state.itemIndex = indexOf(registeredEditor, "mode")
  registeredEditor.handleKey(KEY_RIGHT)

  body = stripAnsi("\n".join(registeredEditor.bodyLines()))
  assert menu.VALUE_DESCRIPTIONS["mode"][config.MODE_EDGE] in body


def test_pathIsShownAndSanitized(dummyVideo, tmp_path):
  """動画の場所が表示され，制御文字が除かれることを確認する."""
  trickyFile = tmp_path / "movie\x1b[31m.mp4"
  trickyFile.write_bytes(b"\x00")
  cli.main(["add", "tricky", str(trickyFile)])

  screen = editor.EntryEditor("tricky", stream=io.StringIO())
  body = "\n".join(screen.bodyLines())
  assert "\x1b[31m" not in body
