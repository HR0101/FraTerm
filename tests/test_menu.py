"""使い方・設定メニューに関するテスト."""

from __future__ import annotations

import io

import pytest

from fraterm import cli, config, diagnostics, menu, settings
from fraterm.textwidth import displayWidth, stripAnsi


def makeMenu() -> menu.Menu:
  """出力を捨てるメニューを作る."""
  return menu.Menu(stream=io.StringIO())


def test_allTabsRenderWithoutError():
  """すべてのタブが例外なく描画できることを確認する."""
  screen = makeMenu()
  for tabIndex in range(len(menu.TABS)):
    screen.state.tabIndex = tabIndex
    lines = screen.renderLines(80, 24)
    assert lines
    assert any(line.strip() for line in lines)


def test_renderedLinesFitInsideWidth():
  """どのタブでも，各行が画面幅を超えないことを確認する."""
  screen = makeMenu()
  width = 60
  for tabIndex in range(len(menu.TABS)):
    screen.state.tabIndex = tabIndex
    for line in screen.renderLines(width, 24):
      assert displayWidth(line) <= width, f"はみ出した行: {stripAnsi(line)!r}"


def test_renderedHeightMatchesTerminal():
  """描画する行数がターミナルの高さと一致することを確認する."""
  screen = makeMenu()
  for height in (12, 24, 40):
    assert len(screen.renderLines(80, height)) == height


def test_tabSwitchingWrapsAround():
  """タブ移動が端で折り返すことを確認する."""
  screen = makeMenu()
  assert screen.state.currentTab == menu.TABS[0]

  screen.handleKey("\t")
  assert screen.state.currentTab == menu.TABS[1]

  screen.state.tabIndex = len(menu.TABS) - 1
  screen.handleKey("\t")
  assert screen.state.currentTab == menu.TABS[0]

  screen.handleKey("h")
  assert screen.state.currentTab == menu.TABS[-1]


def test_arrowKeysMoveSelection():
  """上下の矢印キーで項目を移動できることを確認する."""
  from fraterm.keyboard import KEY_DOWN, KEY_UP

  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_SETTINGS)

  screen.handleKey(KEY_DOWN)
  assert screen.state.itemIndex == 1
  screen.handleKey(KEY_UP)
  assert screen.state.itemIndex == 0

  # 設定タブでは左右は値の増減に使うため，タブは移動しない
  screen.handleKey(KEY_DOWN)
  assert screen.state.currentTab == menu.TAB_SETTINGS


def test_selectionStaysVisibleOnSmallScreen():
  """画面に収まらない場合でも，選択中の項目が必ず表示されることを確認する."""
  from fraterm.keyboard import KEY_DOWN
  from fraterm.textwidth import stripAnsi

  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_SETTINGS)

  # 一番下の項目まで移動する
  for _ in range(len(menu.SETTING_ITEMS) - 1):
    screen.handleKey(KEY_DOWN)

  lines = [stripAnsi(line) for line in screen.renderLines(76, 16)]
  lastItem = menu.SETTING_ITEMS[-1]
  assert any(lastItem.label in line and "▸" in line for line in lines)


def test_scrollIndicatorAppearsWhenContentOverflows():
  """内容が画面に収まらないとき，位置の表示が出ることを確認する."""
  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_SETTINGS)

  screen.renderLines(76, 12)
  assert "/" in screen._scrollIndicator

  screen.renderLines(76, 60)
  assert screen._scrollIndicator == ""


def test_otherTabsScrollWithArrowKeys():
  """設定タブ以外では矢印キーで画面がスクロールすることを確認する."""
  from fraterm.keyboard import KEY_DOWN, KEY_UP
  from fraterm.textwidth import stripAnsi

  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_USAGE)
  firstView = [stripAnsi(line) for line in screen.renderLines(76, 12)]

  screen.handleKey(KEY_DOWN)
  screen.handleKey(KEY_DOWN)
  scrolledView = [stripAnsi(line) for line in screen.renderLines(76, 12)]
  assert firstView != scrolledView

  screen.handleKey(KEY_UP)
  screen.handleKey(KEY_UP)
  assert [stripAnsi(line) for line in screen.renderLines(76, 12)] == firstView


def test_arrowKeysAreNotInsertedIntoInput(isolatedHome):
  """入力欄に矢印キーの文字列が混ざらないことを確認する."""
  from fraterm.keyboard import KEY_DOWN

  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_SETTINGS)
  screen.state.itemIndex = [item.key for item in menu.SETTING_ITEMS].index("width")

  screen.handleKey("\r")
  screen.handleKey("8")
  screen.handleKey(KEY_DOWN)
  screen.handleKey("0")
  screen.handleKey("\r")

  assert settings.load()["width"] == 80


@pytest.mark.parametrize("key", ["q", "Q", "\x1b"])
def test_quitKeysStopMenu(key):
  """q と Esc でメニューを閉じられることを確認する."""
  screen = makeMenu()
  assert screen.handleKey(key) is False


def test_otherKeysKeepMenuOpen():
  """終了以外のキーではメニューが開いたままであることを確認する."""
  screen = makeMenu()
  assert screen.handleKey("j") is True


def test_escapeCancelsEditingInsteadOfQuitting(isolatedHome):
  """値の入力中は，Escが終了ではなく取り消しになることを確認する."""
  screen = settingsScreen("width")
  screen.handleKey("\r")
  screen.handleKey("5")

  # 入力中の Esc はメニューを閉じない
  assert screen.handleKey("\x1b") is True
  assert screen.state.editing is False
  assert "width" not in settings.load()

  # 入力を抜けたあとの Esc は終了になる
  assert screen.handleKey("\x1b") is False


def test_itemMovementOnlyInSettingsTab():
  """項目移動は既定の設定タブでのみ働くことを確認する."""
  screen = makeMenu()
  screen.handleKey("j")
  assert screen.state.itemIndex == 0  # 使い方タブでは動かない

  screen.state.tabIndex = menu.TABS.index(menu.TAB_SETTINGS)
  screen.handleKey("j")
  assert screen.state.itemIndex == 1
  screen.handleKey("k")
  assert screen.state.itemIndex == 0


def test_choiceItemCyclesThroughValues(isolatedHome):
  """選択肢の項目がEnterで順に切り替わることを確認する."""
  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_SETTINGS)
  screen.state.itemIndex = 0  # 描画モード

  screen.handleKey("\r")
  assert settings.load()["mode"] == config.AVAILABLE_MODES[0]

  screen.handleKey("\r")
  assert settings.load()["mode"] == config.AVAILABLE_MODES[1]

  # 末尾まで進めると未設定へ戻る
  for _ in range(len(config.AVAILABLE_MODES) - 1):
    screen.handleKey("\r")
  assert "mode" not in settings.load()


def test_booleanItemCycles(isolatedHome):
  """真偽の項目が未設定・はい・いいえを巡ることを確認する."""
  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_SETTINGS)
  screen.state.itemIndex = [item.key for item in menu.SETTING_ITEMS].index("audio")

  screen.handleKey("\r")
  assert settings.load()["audio"] is True
  screen.handleKey("\r")
  assert settings.load()["audio"] is False
  screen.handleKey("\r")
  assert "audio" not in settings.load()


def test_textItemAcceptsTypedValue(isolatedHome):
  """文字入力の項目に値を入力して保存できることを確認する."""
  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_SETTINGS)
  screen.state.itemIndex = [item.key for item in menu.SETTING_ITEMS].index("width")

  screen.handleKey("\r")
  assert screen.state.editing is True

  for character in "100":
    screen.handleKey(character)
  screen.handleKey("\r")

  assert screen.state.editing is False
  assert settings.load()["width"] == 100


def test_textItemRejectsInvalidNumber(isolatedHome):
  """数値でない入力を保存せず，メッセージで知らせることを確認する."""
  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_SETTINGS)
  screen.state.itemIndex = [item.key for item in menu.SETTING_ITEMS].index("width")

  screen.handleKey("\r")
  for character in "abc":
    screen.handleKey(character)
  screen.handleKey("\r")

  assert "width" not in settings.load()
  assert "読み取れません" in screen.state.message


def test_editingCanBeCancelled(isolatedHome):
  """Escキーで入力を取り消せることを確認する."""
  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_SETTINGS)
  screen.state.itemIndex = [item.key for item in menu.SETTING_ITEMS].index("width")

  screen.handleKey("\r")
  screen.handleKey("5")
  screen.handleKey(menu.terminal.ESC)

  assert screen.state.editing is False
  assert "width" not in settings.load()


def test_backspaceRemovesCharacter(isolatedHome):
  """入力中にBackspaceで1文字消せることを確認する."""
  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_SETTINGS)
  screen.state.itemIndex = [item.key for item in menu.SETTING_ITEMS].index("width")

  screen.handleKey("\r")
  for character in "123":
    screen.handleKey(character)
  screen.handleKey("\x7f")
  screen.handleKey("\r")

  assert settings.load()["width"] == 12


def test_emptyInputClearsValue(isolatedHome):
  """空欄で確定すると設定が未設定へ戻ることを確認する."""
  settings.save({"width": 80})
  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_SETTINGS)
  screen.state.itemIndex = [item.key for item in menu.SETTING_ITEMS].index("width")

  screen.handleKey("\r")
  screen.handleKey("\x7f")
  screen.handleKey("\x7f")
  screen.handleKey("\r")

  assert "width" not in settings.load()


def settingsScreen(key: str) -> menu.Menu:
  """既定の設定タブで，指定した項目を選んだ状態のメニューを作る."""
  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_SETTINGS)
  screen.state.itemIndex = [item.key for item in menu.SETTING_ITEMS].index(key)
  return screen


def test_arrowKeysStepNumericValue(isolatedHome):
  """左右の矢印キーで数値を増減できることを確認する."""
  from fraterm.keyboard import KEY_LEFT, KEY_RIGHT

  screen = settingsScreen("width")
  widthItem = next(item for item in menu.SETTING_ITEMS if item.key == "width")

  # 未設定からの1回目は，その項目の標準的な値から始める
  screen.handleKey(KEY_RIGHT)
  assert settings.load()["width"] == widthItem.base

  screen.handleKey(KEY_RIGHT)
  assert settings.load()["width"] == widthItem.base + widthItem.step

  screen.handleKey(KEY_LEFT)
  assert settings.load()["width"] == widthItem.base


def test_arrowKeysStepDecimalValue(isolatedHome):
  """小数の項目が刻み幅どおりに増減することを確認する."""
  from fraterm.keyboard import KEY_LEFT

  screen = settingsScreen("brightness")
  screen.handleKey(KEY_LEFT)  # 起点の 0.0
  screen.handleKey(KEY_LEFT)
  screen.handleKey(KEY_LEFT)

  # 浮動小数の誤差が残らないよう丸めている
  assert settings.load()["brightness"] == -0.2


@pytest.mark.parametrize("key", ["width", "fps", "brightness", "contrast", "volume", "audioOffset"])
def test_numericValuesStayInRange(isolatedHome, key):
  """増減しても，設定できる範囲を超えないことを確認する."""
  from fraterm.keyboard import KEY_LEFT, KEY_RIGHT

  item = next(entry for entry in menu.SETTING_ITEMS if entry.key == key)

  screen = settingsScreen(key)
  for _ in range(200):
    screen.handleKey(KEY_RIGHT)
  assert settings.load()[key] == item.maximum

  for _ in range(400):
    screen.handleKey(KEY_LEFT)
  assert settings.load()[key] == item.minimum


def test_arrowKeysCycleChoicesBothWays(isolatedHome):
  """選択肢の項目も左右で前後に切り替わることを確認する."""
  from fraterm.keyboard import KEY_LEFT, KEY_RIGHT

  screen = settingsScreen("mode")
  screen.handleKey(KEY_RIGHT)
  assert settings.load()["mode"] == config.AVAILABLE_MODES[0]

  screen.handleKey(KEY_LEFT)
  assert "mode" not in settings.load()  # 未設定へ戻る

  screen.handleKey(KEY_LEFT)
  assert settings.load()["mode"] == config.AVAILABLE_MODES[-1]  # 逆順に巡る


def test_typedInputStillWorksAlongsideArrows(isolatedHome):
  """矢印での増減と，入力して決定する方法の両方が使えることを確認する."""
  from fraterm.keyboard import KEY_RIGHT

  screen = settingsScreen("width")

  # まず矢印で変更する
  screen.handleKey(KEY_RIGHT)
  assert settings.load()["width"] == 80

  # 続けて数値を打ち込んでも上書きできる
  screen.handleKey("\r")
  for character in "\x7f" * 4:
    screen.handleKey(character)
  for character in "150":
    screen.handleKey(character)
  screen.handleKey("\r")
  assert settings.load()["width"] == 150

  # そのあとまた矢印で増減できる
  screen.handleKey(KEY_RIGHT)
  assert settings.load()["width"] == 155


def test_deleteKeyClearsValue(isolatedHome):
  """d キーで項目を未設定へ戻せることを確認する."""
  from fraterm.keyboard import KEY_RIGHT

  screen = settingsScreen("volume")
  screen.handleKey(KEY_RIGHT)
  assert "volume" in settings.load()

  screen.handleKey("d")
  assert "volume" not in settings.load()


def test_tabKeyStillSwitchesTabsInSettings():
  """設定タブでも Tab でタブを移動できることを確認する."""
  screen = settingsScreen("mode")
  screen.handleKey("\t")
  assert screen.state.currentTab != menu.TAB_SETTINGS


def test_arrowKeysSwitchTabsOutsideSettings():
  """設定タブ以外では，左右の矢印がタブ切り替えのままであることを確認する."""
  from fraterm.keyboard import KEY_RIGHT

  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_USAGE)
  screen.handleKey(KEY_RIGHT)
  assert screen.state.currentTab == menu.TABS[1]


def test_numericItemsHaveConsistentRanges():
  """数値項目の設定値（刻み・範囲・起点）が矛盾しないことを確認する."""
  for item in menu.SETTING_ITEMS:
    if not item.isNumeric:
      continue
    assert item.minimum < item.maximum, item.key
    assert item.minimum <= item.base <= item.maximum, item.key
    assert 0 < item.step <= (item.maximum - item.minimum), item.key


def test_valueDescriptionChangesWithValue(isolatedHome):
  """値を変えると，右側の説明もその値の内容へ変わることを確認する."""
  from fraterm.textwidth import stripAnsi

  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_SETTINGS)
  screen.state.itemIndex = 0  # 描画モード

  before = stripAnsi("\n".join(screen.bodyLines()))
  # 未設定のときは，実際の既定値が何かを示す
  assert menu.UNSET_DESCRIPTIONS["mode"] in before

  screen.handleKey("\r")  # ascii
  afterAscii = stripAnsi("\n".join(screen.bodyLines()))
  assert menu.VALUE_DESCRIPTIONS["mode"][config.MODE_ASCII] in afterAscii

  screen.handleKey("\r")  # edge
  afterEdge = stripAnsi("\n".join(screen.bodyLines()))
  assert menu.VALUE_DESCRIPTIONS["mode"][config.MODE_EDGE] in afterEdge
  assert afterAscii != afterEdge


def test_describeValueForNumbers():
  """数値の項目でも，設定した値を含む説明になることを確認する."""
  widthItem = next(item for item in menu.SETTING_ITEMS if item.key == "width")
  description = menu.describeValue(widthItem, 100)

  assert "100" in description
  assert description != widthItem.description


def test_describeValueForUnsetNamesTheDefault():
  """未設定のときに，実際の既定値が分かる説明になることを確認する."""
  modeItem = next(item for item in menu.SETTING_ITEMS if item.key == "mode")
  description = menu.describeValue(modeItem, None)

  assert config.DEFAULT_MODE in description
  assert "未設定" in description


def test_everyItemExplainsItsDefault():
  """すべての項目で，未設定のときの動作が説明されることを確認する."""
  for item in menu.SETTING_ITEMS:
    description = menu.describeValue(item, None)
    assert item.key in menu.UNSET_DESCRIPTIONS, f"既定値の説明がありません: {item.key}"
    assert "標準の動作です" not in description, f"具体的な説明がありません: {item.key}"


@pytest.mark.parametrize(
  "key, expectedFragment",
  [
    ("mode", config.DEFAULT_MODE),
    ("color", config.DEFAULT_COLOR),
    ("quality", config.DEFAULT_QUALITY),
    ("volume", str(config.DEFAULT_VOLUME)),
    ("charset", config.DEFAULT_CHARSET_NAME),
  ],
)
def test_unsetDescriptionShowsActualDefault(key, expectedFragment):
  """未設定の説明に，設定値そのものが含まれることを確認する."""
  assert expectedFragment in menu.UNSET_DESCRIPTIONS[key]


def test_everyChoiceHasDescription():
  """選択肢のある項目は，どの値にも説明が用意されていることを確認する."""
  for item in menu.SETTING_ITEMS:
    if item.kind != "choice":
      continue
    for choice in item.choices:
      description = menu.describeValue(item, choice)
      assert description, f"説明がありません: {item.key}={choice}"
      # 項目の一般説明ではなく，値ごとの説明になっている
      if item.key in menu.VALUE_DESCRIPTIONS or item.key in menu.VALUE_TEMPLATES:
        assert description != item.description


def test_booleanValuesHaveDescriptions():
  """真偽の項目も，はい・いいえそれぞれの説明を持つことを確認する."""
  for item in menu.SETTING_ITEMS:
    if item.kind != "bool":
      continue
    assert menu.describeValue(item, True) != menu.describeValue(item, False)


def test_settingItemsMatchStoredKeys():
  """メニューの項目が，保存できる項目として認められていることを確認する."""
  for item in menu.SETTING_ITEMS:
    assert item.key in settings.ALLOWED_KEYS, f"保存できない項目: {item.key}"


def test_videoTabListsRegisteredEntries(dummyVideo):
  """登録一覧タブに登録済みの動画が並ぶことを確認する."""
  cli.main(["add", "sample", str(dummyVideo)])

  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_VIDEOS)
  body = "\n".join(screen.bodyLines())

  assert "sample" in body
  assert str(dummyVideo) in body


def test_videoTabHandlesBrokenRegistry(isolatedHome):
  """登録データが壊れていてもメニューが開けることを確認する."""
  isolatedHome.mkdir(parents=True, exist_ok=True)
  (isolatedHome / config.REGISTRY_FILE_NAME).write_text("{ broken", encoding="utf-8")

  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_VIDEOS)
  assert screen.bodyLines()


def test_environmentTabShowsDiagnostics():
  """環境タブに診断結果が並ぶことを確認する."""
  screen = makeMenu()
  screen.state.tabIndex = menu.TABS.index(menu.TAB_ENVIRONMENT)
  body = "\n".join(screen.bodyLines())

  assert "OpenCV" in body
  assert "yt-dlp" in body


def test_diagnosticsCollectReturnsItems():
  """診断がすべての項目を返すことを確認する."""
  items = diagnostics.collect()
  labels = {item.label for item in items}

  assert {"Python", "OpenCV", "yt-dlp", "ffplay"} <= labels
  assert all(isinstance(item.available, bool) for item in items)


def test_missingCommandVersionReturnsNone(monkeypatch):
  """存在しないコマンドのバージョン取得が None になることを確認する."""
  monkeypatch.setattr(diagnostics.shutil, "which", lambda name: None)
  assert diagnostics.commandVersion("nonexistent") is None


@pytest.mark.parametrize(
  "value, expected",
  [(None, menu.UNSET_LABEL), (True, "はい"), (False, "いいえ"), (100, "100")],
)
def test_formatValue(value, expected):
  """設定値の表示が読みやすい形になることを確認する."""
  assert menu.formatValue(value) == expected


def test_menuCommandRunsWithoutTerminal(monkeypatch, capsys):
  """キー入力が使えない環境でも menu コマンドが終了することを確認する."""
  assert cli.main(["menu"]) == cli.EXIT_OK


def test_helpAliasOpensMenu(monkeypatch):
  """help という別名でもメニューを開けることを確認する."""
  opened: list[bool] = []

  class FakeMenu:
    def __init__(self, *args, **kwargs) -> None:
      pass

    def run(self) -> None:
      opened.append(True)

  monkeypatch.setattr(menu, "Menu", FakeMenu)
  assert cli.main(["help"]) == cli.EXIT_OK
  assert opened == [True]
