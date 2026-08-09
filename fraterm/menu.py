"""使い方と設定を1画面で確認・変更できるメニューを表示するモジュール."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, TextIO

from . import config, diagnostics, settings, terminal
from .keyboard import KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_UP, KeyReader
from .registry import Registry
from .textwidth import displayWidth, padToWidth, sanitizeText, truncateToWidth

# 画面上部のタブ
TAB_USAGE = "使い方"
TAB_KEYS = "キー操作"
TAB_SETTINGS = "既定の設定"
TAB_VIDEOS = "登録一覧"
TAB_ENVIRONMENT = "環境"
TAB_LANGUAGE = "表示言語"
TABS = (TAB_USAGE, TAB_KEYS, TAB_SETTINGS, TAB_VIDEOS, TAB_ENVIRONMENT, TAB_LANGUAGE)

# 画面の枠に使う文字
HORIZONTAL_LINE = "─"

# ヘッダーとフッターが占める行数
CHROME_ROWS = 5

# 入力待ちの間隔（秒）
POLL_INTERVAL = 0.15

# 値を編集するときの最大文字数
MAX_INPUT_LENGTH = 60

# 既定の設定タブで，項目一覧が始まるまでの説明行の数
SETTINGS_HEADER_LINES = 3

# 未設定を表す表示
UNSET_LABEL = "未設定"

# 対応している表示言語（英語対応は今後の課題）
AVAILABLE_LANGUAGES = ("日本語",)

ENTER_KEYS = ("\r", "\n")
BACKSPACE_KEYS = ("\x7f", "\x08")

# 入力中でも「確定してから動く」キー
ARROW_KEYS = (KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT)


@dataclass
class SettingItem:
  """既定値として設定できる項目1件."""

  key: str
  label: str
  kind: str  # "choice"，"bool"，"text" のいずれか
  description: str
  choices: tuple[Any, ...] = ()
  # 数値項目で，矢印キーの増減に使う設定
  step: float = 0.0
  minimum: float = 0.0
  maximum: float = 0.0
  # 未設定から増減を始めるときの起点
  base: float = 0.0
  # 小数点以下の桁数．0なら整数として扱う
  decimals: int = 0

  @property
  def isNumeric(self) -> bool:
    """矢印キーで増減できる数値項目かどうかを返す."""
    return self.kind == "text" and self.step > 0


# 既定の設定タブに並べる項目
SETTING_ITEMS: tuple[SettingItem, ...] = (
  SettingItem("mode", "描画モード", "choice", "文字・線画・カラーの切り替え", config.AVAILABLE_MODES),
  SettingItem("charset", "文字セット", "choice", "濃淡に使う文字", tuple(config.CHARSET_PRESETS)),
  SettingItem("color", "文字の着色", "choice", "文字自体に色を付ける", config.COLOR_CHOICES),
  SettingItem(
    "width", "最大表示幅", "text", "桁数．空欄でターミナル幅に追従",
    step=5, minimum=10, maximum=500, base=80,
  ),
  SettingItem(
    "fps", "FPS上限", "text", "描画の上限．空欄で動画のFPSに従う",
    step=5, minimum=1, maximum=120, base=30,
  ),
  SettingItem(
    "preRender", "再生前に事前生成", "bool",
    "全フレームを先に文字列化して再生中の変換遅延を抑える",
  ),
  SettingItem(
    "brightness", "明るさ", "text", "-1.0 〜 1.0 の補正値",
    step=0.1, minimum=-1.0, maximum=1.0, base=0.0, decimals=2,
  ),
  SettingItem(
    "contrast", "コントラスト", "text", "0.1 〜 5.0 の補正値",
    step=0.1, minimum=0.1, maximum=5.0, base=1.0, decimals=2,
  ),
  SettingItem("audio", "音声再生", "bool", "ffplay で音声を鳴らす"),
  SettingItem(
    "volume", "音量", "text", "0 〜 100",
    step=config.VOLUME_STEP, minimum=config.MIN_VOLUME, maximum=config.MAX_VOLUME,
    base=config.DEFAULT_VOLUME,
  ),
  SettingItem(
    "audioOffset", "音声のずれ補正", "text", "秒．正の値で音声が先行",
    step=0.1, minimum=config.MIN_AUDIO_OFFSET, maximum=config.MAX_AUDIO_OFFSET,
    base=0.0, decimals=2,
  ),
  SettingItem("quality", "URLの画質", "choice", "URL再生時に取得する画質", config.QUALITY_CHOICES),
  SettingItem("cache", "URLを保存して再生", "bool", "ダウンロードしてから再生する"),
  SettingItem(
    "cookiesFromBrowser",
    "Cookieの取得元",
    "choice",
    "年齢制限などでログイン情報を使う",
    config.SUPPORTED_COOKIE_BROWSERS,
  ),
)


# 値ごとの説明．選んだ値でどう変わるかを右側へ表示する
VALUE_DESCRIPTIONS: dict[str, dict[Any, str]] = {
  "mode": {
    config.MODE_ASCII: "明るさに応じた文字で描きます（標準）",
    config.MODE_EDGE: "輪郭を | / - \\ の記号で描く白黒の線画になります",
    config.MODE_COLOR: "ブロック文字のカラー表示．モザイク調になります",
    config.MODE_MONO: "ブロック文字の白黒表示になります",
  },
  "charset": {
    "standard": "23階調．濃淡のバランスが良い既定の文字です",
    "detailed": "70階調．最も密で細かく，情報量が増えます",
    "simple": "10階調．すっきりした見た目になります",
    "blocks": "░▒▓█ のブロックで塗ります",
    "minimal": "4階調．軽く，粗い表現になります",
  },
  "color": {
    config.COLOR_OFF: "着色しません．白黒の文字だけで表示します",
    config.COLOR_256: "256色で文字を着色します．tmux 経由でも安定します",
    config.COLOR_TRUE: "24bitカラーで着色します．最もなめらかです",
  },
  "quality": {
    "360": "360p まで．取得が速く，端末表示では十分です",
    "480": "480p まで．画質と速度のつり合いが良い既定値です",
    "720": "720p まで．入手できない場合は自動的に下げます",
    "1080": "1080p まで．入手できない場合は自動的に下げます",
    "best": "入手できる中で最も高い画質を選びます",
    "worst": "入手できる中で最も低い画質を選びます．取得が最速です",
  },
  "audio": {
    True: "ffplay で音声も鳴らします",
    False: "音声を鳴らしません",
  },
  "preRender": {
    True: "再生開始前に全フレームを生成し，途中のカクつきを抑えます",
    False: "再生しながらフレームを変換します",
  },
  "cache": {
    True: "ダウンロードしてから再生します．次回からオフラインでも見られます",
    False: "ダウンロードせず直接ストリーミングします",
  },
}

# 数値・文字列の項目で，設定した値を説明する文
VALUE_TEMPLATES: dict[str, str] = {
  "width": "{value} 桁までに抑えて描画します（端末が狭ければそちらに合わせます）",
  "fps": "1秒あたり最大 {value} 回だけ描き直します．負荷を下げられます",
  "brightness": "明るさを {value} だけ加算します（正で明るく，負で暗く）",
  "contrast": "明暗の差を {value} 倍にします（1.0 が補正なし）",
  "volume": "音量を {value}% で再生します",
  "audioOffset": "音声を {value} 秒ずらします（正の値で音声が先行）",
  "cookiesFromBrowser": "{value} のログイン情報を使い，年齢制限などの動画も再生します",
}


# 未設定のときに実際どう動くかの説明．既定値そのものを示す
UNSET_DESCRIPTIONS: dict[str, str] = {
  "mode": (
    f"未設定なら {config.DEFAULT_MODE}: "
    f"{VALUE_DESCRIPTIONS['mode'][config.DEFAULT_MODE]}"
  ),
  "charset": (
    f"未設定ならモードに合わせます: ascii は {config.DEFAULT_CHARSET_NAME}（23階調），"
    f"edge は薄い「{config.DEFAULT_EDGE_CHARSET}」"
  ),
  "color": (
    f"未設定なら {config.DEFAULT_COLOR}: "
    f"{VALUE_DESCRIPTIONS['color'][config.DEFAULT_COLOR]}"
  ),
  "width": "未設定ならターミナルの幅いっぱいに描きます",
  "fps": "未設定なら動画のFPSに合わせて描きます（上限を設けません）",
  "preRender": "未設定なら再生しながら変換します（待ち時間なしで始まります）",
  "brightness": f"未設定なら {config.DEFAULT_BRIGHTNESS:g}（明るさを補正しません）",
  "contrast": f"未設定なら {config.DEFAULT_CONTRAST:g}（明暗の差を変えません）",
  "audio": "未設定なら音声を鳴らしません（映像だけ再生します）",
  "volume": f"未設定なら {config.DEFAULT_VOLUME}%（そのままの音量で鳴らします）",
  "audioOffset": (
    f"未設定なら {config.DEFAULT_AUDIO_OFFSET:g}秒（映像と音声をずらしません）"
  ),
  "quality": (
    f"未設定なら {config.DEFAULT_QUALITY}: "
    f"{VALUE_DESCRIPTIONS['quality'][config.DEFAULT_QUALITY]}"
  ),
  "cache": "未設定ならダウンロードせず，直接ストリーミングします",
  "cookiesFromBrowser": "未設定ならログイン情報を使いません（公開動画のみ再生できます）",
  "cookiesFile": "未設定ならCookieファイルを使いません",
  "playerClient": "未設定なら yt-dlp の判断に任せます（通常はこのままで問題ありません）",
}


def describeValue(item: SettingItem, value: Any) -> str:
  """設定した値でどう変わるかの説明を返す."""
  if value is None:
    # 「標準の動作」が何かを具体的に示す
    unsetDescription = UNSET_DESCRIPTIONS.get(item.key)
    if unsetDescription is not None:
      return unsetDescription
    return f"{item.description}（未設定のときは標準の動作です）"

  descriptions = VALUE_DESCRIPTIONS.get(item.key, {})
  if value in descriptions:
    return descriptions[value]

  template = VALUE_TEMPLATES.get(item.key)
  if template is not None:
    return template.format(value=value)

  return item.description


def usageLines() -> list[str]:
  """使い方タブの内容を組み立てる."""
  name = config.commandName()
  return [
    "動画をターミナルで再生するツールです．登録しておけば名前だけで呼び出せます．",
    "",
    f"{terminal.BOLD}基本操作{terminal.RESET_ATTRIBUTES}",
    f"  {name} run <ファイル または URL>      登録せずに再生する",
    f"  {name} add <名前> <ファイル/URL>       名前を付けて登録する",
    f"  {name} <名前>                          登録した動画を再生する",
    f"  {name} list                            登録一覧を表示する",
    f"  {name} show <名前>                     登録内容の詳細を見る",
    f"  {name} edit <名前>                     設定を選んで変更する（画面が開きます）",
    f"  {name} remove <名前>                   登録を削除する",
    "",
    f"{terminal.BOLD}その他{terminal.RESET_ATTRIBUTES}",
    f"  {name} defaults                        毎回のオプションの既定値を設定する",
    f"  {name} cache                           ダウンロード済み動画を管理する",
    f"  {name} menu                            この画面を開く",
    "",
    f"{terminal.BOLD}短縮形{terminal.RESET_ATTRIBUTES}",
    "  -m モード / -s 文字セット / -c 着色 / -w 幅 / -a 音声 / -q 画質 / -b ブラウザ",
    "",
    f"{terminal.BOLD}例{terminal.RESET_ATTRIBUTES}",
    f'  {name} run "https://youtu.be/XXXXXXXXXXX" -m ascii -s detailed -c true',
    f"  {name} defaults -m ascii -s detailed -c true    # 以降は指定を省略できる",
    "",
    f"コマンド名は {config.APP_NAME} と {config.SHORT_COMMAND_NAME} のどちらでも使えます．",
  ]


def keyLines() -> list[str]:
  """キー操作タブの内容を組み立てる."""
  return [
    "再生中は次のキーが使えます．",
    "",
    "  q / Esc    再生を終了する",
    "  Space      一時停止・再開",
    "  r          先頭から再生し直す",
    "  m          消音の切り替え（--audio 指定時）",
    "  ← / →      10秒ずつ前後へ移動（h / l でも同じ）",
    "  0〜9        動画の0〜90%の位置へ移動（長さが分かる場合）",
    "  + / -      再生速度を上げる・下げる",
    "  [ / ]      音量を下げる・上げる（--audio 指定時）",
    "  s          再生中の動画を保存して登録する",
    "",
    "画面下部の案内は幅に合わせて減るため，狭い画面では一部しか出ません．",
    "使えるキーはここに書いてあるものが全てです．",
    "",
    "s を押すと保存名の入力欄が出ます．URLを再生中なら動画をダウンロードするため，",
    "そのあとはネットに接続していなくても再生できます．",
    "",
    "このメニューの操作:",
    "  Tab        次のタブへ",
    "  ↑ ↓        項目の移動・画面のスクロール（k j でも同じ）",
    "  ← →        タブを切り替える（h l でも同じ）",
    "  q / Esc    メニューを閉じる",
    "",
    "既定の設定タブでは，← → の意味が変わります:",
    "  ← →        選択中の項目の値を増減する（数値は1段階ずつ）",
    "  Enter      選択肢は次の値へ．数値・文字列は入力欄を開く",
    "  d          その項目を未設定へ戻す",
    "  Esc        入力中の値を取り消す",
  ]


def languageLines() -> list[str]:
  """表示言語タブの内容を組み立てる."""
  return [
    "現在の表示言語: 日本語",
    "",
    "メッセージ・ヘルプ・この画面はすべて日本語で表示されます．",
    "英語など他の言語への切り替えには対応していません．",
    "",
    "対応言語:",
    *[f"  ・{language}" for language in AVAILABLE_LANGUAGES],
    "",
    "数字や記号の表記は環境の設定にかかわらず共通です．",
    "全角文字を含む表示は，文字幅を考慮して折り返し・切り詰めを行います．",
  ]


@dataclass
class MenuState:
  """メニューの選択状態を保持するデータクラス."""

  tabIndex: int = 0
  itemIndex: int = 0
  scrollOffset: int = 0
  message: str = ""
  editing: bool = False
  editBuffer: str = ""
  # 環境の診断は時間がかかるため，開いたときに一度だけ調べる
  diagnosticItems: list[diagnostics.DiagnosticItem] = field(default_factory=list)

  @property
  def currentTab(self) -> str:
    """選択中のタブ名を返す."""
    return TABS[self.tabIndex % len(TABS)]

  def moveTab(self, delta: int) -> None:
    """タブを切り替える."""
    self.tabIndex = (self.tabIndex + delta) % len(TABS)
    self.itemIndex = 0
    self.scrollOffset = 0
    self.message = ""

  def moveItem(self, delta: int) -> None:
    """項目の選択を移動する."""
    if self.currentTab != TAB_SETTINGS:
      return
    self.itemIndex = (self.itemIndex + delta) % len(SETTING_ITEMS)

  @property
  def currentItem(self) -> SettingItem | None:
    """既定の設定タブで選択中の項目を返す."""
    if self.currentTab != TAB_SETTINGS:
      return None
    return SETTING_ITEMS[self.itemIndex % len(SETTING_ITEMS)]


def formatValue(value: Any) -> str:
  """設定値を表示用の文字列へ変換する."""
  if value is None:
    return UNSET_LABEL
  if isinstance(value, bool):
    return "はい" if value else "いいえ"
  return str(value)


def parseTextValue(item: SettingItem, rawValue: str) -> Any:
  """入力された文字列を，項目に応じた値へ変換する.

  数値は設定できる範囲へ収める．範囲外の値をそのまま保存すると，
  コマンドから指定した場合には拒否される値が既定値に残ってしまう.
  """
  text = rawValue.strip()
  if not text:
    return None

  if item.key in ("width", "volume"):
    return clampNumber(item, int(text))
  if item.key in ("fps", "brightness", "contrast", "audioOffset"):
    return clampNumber(item, float(text))
  return text


def clampNumber(item: SettingItem, value: float) -> Any:
  """数値を項目の範囲へ収める."""
  if not item.isNumeric:
    return value

  clamped = max(item.minimum, min(item.maximum, value))
  if item.decimals > 0:
    return round(clamped, item.decimals)
  return int(round(clamped))


def nextChoice(item: SettingItem, currentValue: Any) -> Any:
  """選択肢を1つ進める．末尾の次は未設定へ戻る."""
  options: list[Any] = [None, *item.choices]
  try:
    currentIndex = options.index(currentValue)
  except ValueError:
    currentIndex = 0
  return options[(currentIndex + 1) % len(options)]


def nextBoolean(currentValue: Any) -> Any:
  """未設定・はい・いいえを順に切り替える."""
  if currentValue is None:
    return True
  if currentValue is True:
    return False
  return None


def stepNumber(item: SettingItem, currentValue: Any, direction: int) -> Any:
  """数値の項目を，矢印キーの向きに応じて増減する.

  未設定のときは，その項目の標準的な値から始める.
  """
  if currentValue is None:
    startValue = item.base
  else:
    try:
      startValue = float(currentValue)
    except (TypeError, ValueError):
      startValue = item.base
    startValue += item.step * direction

  clamped = max(item.minimum, min(item.maximum, startValue))
  if item.decimals > 0:
    return round(clamped, item.decimals)
  return int(round(clamped))


def adjustValue(item: SettingItem, currentValue: Any, direction: int) -> Any:
  """左右の矢印キーで，項目の値を1段階変更する."""
  if item.kind == "choice":
    options: list[Any] = [None, *item.choices]
    try:
      currentIndex = options.index(currentValue)
    except ValueError:
      currentIndex = 0
    return options[(currentIndex + direction) % len(options)]

  if item.kind == "bool":
    # 未設定・はい・いいえを順に巡る
    states: list[Any] = [None, True, False]
    try:
      currentIndex = states.index(currentValue)
    except ValueError:
      currentIndex = 0
    return states[(currentIndex + direction) % len(states)]

  if item.isNumeric:
    return stepNumber(item, currentValue, direction)

  return currentValue


class Menu:
  """使い方と設定を表示する全画面メニュー."""

  def __init__(self, stream: TextIO | None = None) -> None:
    self.stream = stream or sys.stdout
    self.state = MenuState()
    # 直近の描画で求めたスクロール位置の表示
    self._scrollIndicator = ""

  # ---------------------------------------------------------------------
  # 表示
  # ---------------------------------------------------------------------

  def tabLine(self, width: int) -> str:
    """タブの並びを組み立てる."""
    parts = []
    for index, name in enumerate(TABS):
      if index == self.state.tabIndex:
        parts.append(f"{terminal.REVERSE} {name} {terminal.RESET_ATTRIBUTES}")
      else:
        parts.append(f" {name} ")
    return truncateToWidth("".join(parts), width)

  def bodyLines(self) -> list[str]:
    """選択中のタブの本文を組み立てる."""
    tab = self.state.currentTab
    if tab == TAB_USAGE:
      return usageLines()
    if tab == TAB_KEYS:
      return keyLines()
    if tab == TAB_SETTINGS:
      return self.settingLines()
    if tab == TAB_VIDEOS:
      return self.videoLines()
    if tab == TAB_ENVIRONMENT:
      return self.environmentLines()
    return languageLines()

  def settingLines(self) -> list[str]:
    """既定の設定タブの内容を組み立てる."""
    values = settings.load()
    labelWidth = max(displayWidth(item.label) for item in SETTING_ITEMS)

    lines = [
      "毎回のオプションを省略するための既定値です．run と add に適用されます．",
      "← → で変更（その場で保存されます），Enter で直接入力，d で未設定へ戻します．",
      "",
    ]
    for index, item in enumerate(SETTING_ITEMS):
      marker = "▸" if index == self.state.itemIndex else " "
      storedValue = values.get(item.key)
      value = formatValue(storedValue)
      row = f"{marker} {padToWidth(item.label, labelWidth)}  {padToWidth(value, 12)}"

      # 右側には，いま選んでいる値でどう変わるかを書く
      explanation = describeValue(item, storedValue)
      if index == self.state.itemIndex:
        lines.append(f"{terminal.BOLD}{row}{terminal.RESET_ATTRIBUTES}  {explanation}")
      else:
        lines.append(f"{row}  {terminal.DIM}{explanation}{terminal.RESET_ATTRIBUTES}")

    lines.append("")
    lines.append(f"{terminal.DIM}保存先: {settings.settingsPath()}{terminal.RESET_ATTRIBUTES}")
    return lines

  def videoLines(self) -> list[str]:
    """登録一覧タブの内容を組み立てる."""
    try:
      entries = Registry().load()
    except Exception as error:  # 壊れた登録データでもメニューは開けるようにする
      return [f"登録データを読み込めません: {error}"]

    if not entries:
      return [
        "登録されている動画はありません．",
        "",
        f"  {config.commandName()} add <名前> <ファイル/URL>  で登録できます．",
      ]

    lines = [f"登録数: {len(entries)}", ""]
    nameWidth = max(len(name) for name in entries)
    for name, entry in sorted(entries.items()):
      location = sanitizeText(entry.path)
      marker = "URL" if entry.isRemote else "   "
      lines.append(f"  {padToWidth(name, nameWidth)}  {entry.mode:<6} {marker}  {location}")
    return lines

  def environmentLines(self) -> list[str]:
    """環境タブの内容を組み立てる."""
    if not self.state.diagnosticItems:
      self.state.diagnosticItems = diagnostics.collect()

    labelWidth = max(displayWidth(item.label) for item in self.state.diagnosticItems)
    lines = ["依存ツールと保存先の状態です．", ""]
    for item in self.state.diagnosticItems:
      lines.append(f"  {item.statusMark()} {padToWidth(item.label, labelWidth)}  {item.detail}")
      if item.hint:
        lines.append(f"      {terminal.DIM}→ {item.hint}{terminal.RESET_ATTRIBUTES}")
    return lines

  def footerLine(self, width: int) -> str:
    """画面下部の操作説明を組み立てる."""
    if self.state.editing:
      item = self.state.currentItem
      label = item.label if item else ""
      return truncateToWidth(
        f"{label}: {self.state.editBuffer}_  "
        f"[Enter]決定 [↑↓]確定して移動 [Esc]取消",
        width,
      )

    if self.state.message:
      return truncateToWidth(self.state.message, width)

    indicator = getattr(self, "_scrollIndicator", "")
    position = f" {indicator}" if indicator else ""

    if self.state.currentTab == TAB_SETTINGS:
      return truncateToWidth(
        f"[Tab]切替 [↑↓]移動 [←→]増減 [Enter]入力 [d]未設定 [q/Esc]終了{position}",
        width,
      )
    return truncateToWidth(
      f"[Tab/←→]タブ切替 [↑↓]スクロール [q/Esc]終了{position}", width
    )

  def _moveDown(self) -> None:
    """1つ下へ移動する（設定タブ以外はスクロールする）."""
    if self.state.currentTab == TAB_SETTINGS:
      self.state.moveItem(1)
      return
    self.state.scrollOffset += 1

  def _moveUp(self) -> None:
    """1つ上へ移動する（設定タブ以外はスクロールする）."""
    if self.state.currentTab == TAB_SETTINGS:
      self.state.moveItem(-1)
      return
    self.state.scrollOffset = max(0, self.state.scrollOffset - 1)

  def _scrollWindow(self, lines: list[str], bodyHeight: int) -> list[str]:
    """選択中の項目が必ず見えるように，表示範囲を切り出す."""
    maxOffset = max(0, len(lines) - bodyHeight)

    if self.state.currentTab == TAB_SETTINGS:
      # 選択行が画面の外に出たら，その分だけ表示範囲をずらす
      selectedLine = SETTINGS_HEADER_LINES + self.state.itemIndex
      if selectedLine < self.state.scrollOffset:
        self.state.scrollOffset = selectedLine
      elif selectedLine >= self.state.scrollOffset + bodyHeight:
        self.state.scrollOffset = selectedLine - bodyHeight + 1

    self.state.scrollOffset = max(0, min(self.state.scrollOffset, maxOffset))
    return lines[self.state.scrollOffset : self.state.scrollOffset + bodyHeight]

  def scrollIndicator(self, totalLines: int, bodyHeight: int) -> str:
    """画面に収まらない場合に，現在位置を示す文字列を返す."""
    if totalLines <= bodyHeight:
      return ""
    lastLine = min(totalLines, self.state.scrollOffset + bodyHeight)
    return f"[{self.state.scrollOffset + 1}-{lastLine}/{totalLines}]"

  def renderLines(self, width: int, height: int) -> list[str]:
    """画面全体の行を組み立てる."""
    bodyHeight = max(1, height - CHROME_ROWS)
    allLines = self.bodyLines()
    body = self._scrollWindow(allLines, bodyHeight)
    self._scrollIndicator = self.scrollIndicator(len(allLines), bodyHeight)
    body += [""] * (bodyHeight - len(body))

    return [
      truncateToWidth(
        f"{terminal.BOLD}FraTerm {config.VERSION}{terminal.RESET_ATTRIBUTES}"
        f"  {terminal.DIM}使い方と設定{terminal.RESET_ATTRIBUTES}",
        width,
      ),
      self.tabLine(width),
      HORIZONTAL_LINE * width,
      *[truncateToWidth(line, width) for line in body],
      HORIZONTAL_LINE * width,
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

    # Esc でも閉じられる（値の入力中は _handleEditKey が先に取り消しへ使う）
    if key in ("q", "Q") or key == terminal.ESC:
      return False
    if key == "\t":
      self.state.moveTab(1)
      return True
    if key in ("h", KEY_LEFT):
      # 設定タブでは，左右で値そのものを増減する
      if self.state.currentTab == TAB_SETTINGS:
        self._adjustSelected(-1)
      else:
        self.state.moveTab(-1)
      return True
    if key in ("l", KEY_RIGHT):
      if self.state.currentTab == TAB_SETTINGS:
        self._adjustSelected(1)
      else:
        self.state.moveTab(1)
      return True
    if key == "d" and self.state.currentTab == TAB_SETTINGS:
      self._clearSelected()
      return True
    if key in ("j", KEY_DOWN):
      self._moveDown()
      return True
    if key in ("k", KEY_UP):
      self._moveUp()
      return True
    if key in ENTER_KEYS:
      self._activateItem()
      return True

    return True

  def _handleEditKey(self, key: str) -> bool:
    """値の入力中のキーを処理する."""
    if key in ARROW_KEYS:
      # 入力をそのまま確定し，矢印キー本来の移動・増減へ進む
      self._commitEdit()
      return self.handleKey(key)

    if key == terminal.ESC:
      self.state.editing = False
      self.state.editBuffer = ""
      self.state.message = "変更を取り消しました．"
      return True

    if key in ENTER_KEYS:
      self._commitEdit()
      return True

    if key in BACKSPACE_KEYS:
      self.state.editBuffer = self.state.editBuffer[:-1]
      return True

    if len(key) == 1 and key.isprintable() and len(self.state.editBuffer) < MAX_INPUT_LENGTH:
      self.state.editBuffer += key
    return True

  def _adjustSelected(self, direction: int) -> None:
    """選択中の項目を，左右キーで1段階変更する."""
    item = self.state.currentItem
    if item is None:
      return

    currentValue = settings.load().get(item.key)
    newValue = adjustValue(item, currentValue, direction)
    if newValue == currentValue:
      return
    self._storeValue(item, newValue)

  def _clearSelected(self) -> None:
    """選択中の項目を未設定へ戻す."""
    item = self.state.currentItem
    if item is None:
      return
    self._storeValue(item, None)

  def _activateItem(self) -> None:
    """選択中の項目を変更する."""
    item = self.state.currentItem
    if item is None:
      return

    values = settings.load()
    currentValue = values.get(item.key)

    if item.kind == "choice":
      self._storeValue(item, nextChoice(item, currentValue))
      return
    if item.kind == "bool":
      self._storeValue(item, nextBoolean(currentValue))
      return

    self.state.editing = True
    self.state.editBuffer = "" if currentValue is None else str(currentValue)
    self.state.message = ""

  def _commitEdit(self) -> None:
    """入力された値を保存する."""
    item = self.state.currentItem
    self.state.editing = False
    if item is None:
      return

    try:
      value = parseTextValue(item, self.state.editBuffer)
    except ValueError:
      self.state.message = f"「{self.state.editBuffer}」は数値として読み取れません．"
      self.state.editBuffer = ""
      return

    self.state.editBuffer = ""
    self._storeValue(item, value)

  def _storeValue(self, item: SettingItem, value: Any) -> None:
    """設定値を保存し，結果をメッセージへ残す."""
    try:
      if value is None:
        stored = settings.load()
        stored.pop(item.key, None)
        settings.save(stored)
      else:
        settings.update({item.key: value})
    except Exception as error:  # 保存に失敗してもメニューは続ける
      self.state.message = f"保存できませんでした: {error}"
      return

    self.state.message = f"{item.label} を {formatValue(value)} にしました．"

  # ---------------------------------------------------------------------
  # 実行
  # ---------------------------------------------------------------------

  def run(self) -> None:
    """メニューを表示し，キー操作を受け付ける."""
    terminal.enterFullScreen(self.stream)
    try:
      with KeyReader() as keyReader:
        if not keyReader.enabled:
          # キー入力を扱えない環境では，そのまま1画面だけ表示する
          self.draw()
          return

        self.draw()
        while True:
          key = keyReader.readKey(POLL_INTERVAL)
          if key is None:
            continue
          if not self.handleKey(key):
            return
          self.draw()
    finally:
      terminal.leaveFullScreen(self.stream)
