"""再生制御と表示補助に関するテスト."""

from __future__ import annotations

import io

import pytest

from fraterm import audio, config
from fraterm.errors import AudioError, PlaybackError, VideoFileError
from fraterm.player import PlaybackOptions, Player, formatTime
from fraterm.registry import VideoEntry
from fraterm.textwidth import displayWidth, padToWidth, truncateToWidth


@pytest.mark.parametrize(
  "seconds, expected",
  [(0, "00:00"), (5, "00:05"), (65, "01:05"), (3661, "1:01:01"), (-1, "--:--")],
)
def test_formatTime(seconds, expected):
  """秒数が時刻表記へ変換されることを確認する."""
  assert formatTime(seconds) == expected


def test_displayWidthCountsWideCharacters():
  """全角文字が2文字分として数えられることを確認する."""
  assert displayWidth("abc") == 3
  assert displayWidth("再生中") == 6


def test_truncateToWidthKeepsLimit():
  """表示幅の上限を超えないように切り詰められることを確認する."""
  assert displayWidth(truncateToWidth("再生中です", 5)) <= 5
  assert truncateToWidth("abcdef", 3) == "abc"
  assert truncateToWidth("abc", 0) == ""


def test_padToWidthFillsWithSpaces():
  """表示幅がそろうように空白が追加されることを確認する."""
  assert padToWidth("abc", 5) == "abc  "
  assert displayWidth(padToWidth("音声", 6)) == 6


def test_playbackOptionsFromEntry(dummyVideo):
  """登録情報から再生設定が作られることを確認する."""
  entry = VideoEntry(
    name="sample",
    path=str(dummyVideo),
    mode="color",
    audio=True,
    width=120,
    fps=24.0,
    charset="simple",
  )
  options = PlaybackOptions.fromEntry(entry)

  assert options.mode == "color"
  assert options.audio is True
  assert options.width == 120
  assert options.fps == 24.0
  assert options.charset == "simple"
  assert options.title == "sample"


def test_quitKeyStopsPlayback(dummyVideo):
  """q キーが再生終了を要求することを確認する."""
  player = Player(dummyVideo)
  assert player._handleKey("q") is False
  assert player._handleKey("Q") is False
  assert player._handleKey("x") is True


def test_pauseFreezesMediaTime(dummyVideo):
  """一時停止中に再生位置が進まないことを確認する."""
  player = Player(dummyVideo)
  player._startClock()
  player._togglePause()

  firstPosition = player._mediaTime()
  secondPosition = player._mediaTime()
  assert firstPosition == secondPosition

  player._togglePause()
  assert player._paused is False


def test_speedChangeIsClamped(dummyVideo):
  """再生速度が上下限の範囲に収まることを確認する."""
  player = Player(dummyVideo)
  player._startClock()

  for _ in range(50):
    player._changeSpeed(config.SPEED_STEP)
  assert player._speed == config.MAX_SPEED

  for _ in range(50):
    player._changeSpeed(-config.SPEED_STEP)
  assert player._speed == config.MIN_SPEED


def test_missingVideoRaises(tmp_path):
  """存在しない動画を再生しようとした場合のエラーを確認する."""
  with pytest.raises(VideoFileError):
    Player(tmp_path / "none.mp4", stream=io.StringIO()).play()


def test_unreadableVideoRaises(dummyVideo):
  """読み込めない動画ファイルでエラーになることを確認する."""
  with pytest.raises(PlaybackError):
    Player(dummyVideo, stream=io.StringIO()).play()


def test_audioRequiresFfplay(dummyVideo, monkeypatch):
  """ffplay が無い状態で --audio を指定した場合のエラーを確認する."""
  monkeypatch.setattr(audio, "isAvailable", lambda: False)
  options = PlaybackOptions(audio=True)

  with pytest.raises(AudioError):
    Player(dummyVideo, options, stream=io.StringIO()).play()


@pytest.mark.parametrize("mode", config.AVAILABLE_MODES)
def test_playSampleVideoToStream(sampleVideo, mode):
  """実際の動画を最後まで再生し，出力と後始末を確認する."""
  stream = io.StringIO()
  options = PlaybackOptions(mode=mode, width=40, title="sample")

  Player(sampleVideo, options, stream=stream).play()
  output = stream.getvalue()

  assert output, "フレームが出力されていません"
  assert "\x1b[H" in output  # カーソル位置の指定が含まれる
  assert output.endswith("\x1b[0m\n")  # 文字色を戻して終了している


def test_playRespectsFpsLimit(sampleVideo):
  """FPS上限を指定すると描画回数が減ることを確認する."""
  baseStream = io.StringIO()
  Player(sampleVideo, PlaybackOptions(width=40), stream=baseStream).play()

  limitedStream = io.StringIO()
  Player(sampleVideo, PlaybackOptions(width=40, fps=2), stream=limitedStream).play()

  baseFrames = baseStream.getvalue().count("\x1b[H")
  limitedFrames = limitedStream.getvalue().count("\x1b[H")
  assert limitedFrames < baseFrames


class ScriptedKeyReader:
  """待機のたびに，あらかじめ決めたキーを返すテスト用の入力クラス."""

  def __init__(self, keys) -> None:
    self.keys = list(keys)
    self.pressedKeys: list[str] = []

  def __enter__(self) -> "ScriptedKeyReader":
    return self

  def __exit__(self, *exceptionInfo) -> bool:
    return False

  @property
  def enabled(self) -> bool:
    return True

  def readKey(self, timeout: float = 0.0):
    # 待機を伴う読み出しのときだけキーを返す（即時ポーリングでは何も返さない）
    if timeout <= 0:
      return None
    # キーを使い切った場合は，テストが止まらないよう終了キーを返す
    key = self.keys.pop(0) if self.keys else "q"
    self.pressedKeys.append(key)
    return key


def test_pausedPlaybackStillAcceptsKeys(sampleVideo, monkeypatch):
  """一時停止中のキー入力が取りこぼされないことを確認する."""
  import fraterm.player as playerModule

  scriptedReader = ScriptedKeyReader([" ", "q"])
  monkeypatch.setattr(playerModule, "KeyReader", lambda: scriptedReader)

  player = Player(sampleVideo, PlaybackOptions(width=20), stream=io.StringIO())
  player.play()

  assert scriptedReader.pressedKeys == [" ", "q"]
  assert player._paused is True


def test_restartKeyReturnsToBeginning(sampleVideo, monkeypatch):
  """r キーで再生位置が先頭へ戻ることを確認する."""
  import fraterm.player as playerModule

  scriptedReader = ScriptedKeyReader(["r", "q"])
  monkeypatch.setattr(playerModule, "KeyReader", lambda: scriptedReader)

  player = Player(sampleVideo, PlaybackOptions(width=20), stream=io.StringIO())
  player.play()

  assert player._nextFrameIndex <= 1
  assert player._mediaBase == 0.0


@pytest.mark.parametrize(
  "speed, expectedFilterCount",
  [(1.5, 1), (3.0, 2), (0.25, 2)],
)
def test_buildTempoFilter(speed, expectedFilterCount):
  """再生速度に応じた atempo フィルタが組み立てられることを確認する."""
  filterText = audio.buildTempoFilter(speed)
  assert filterText.count("atempo=") == expectedFilterCount


def test_buildTempoFilterKeepsTotalSpeed():
  """連結した atempo の積が指定速度と一致することを確認する."""
  filterText = audio.buildTempoFilter(4.0)
  total = 1.0
  for part in filterText.split(","):
    total *= float(part.split("=")[1])
  assert total == pytest.approx(4.0, rel=1e-3)
