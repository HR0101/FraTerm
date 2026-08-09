"""数字キーによる再生位置移動のテスト."""

from __future__ import annotations

import io

import pytest

from fraterm import config
from fraterm.player import PlaybackOptions, Player


@pytest.mark.parametrize(
  "key, expectedFraction",
  [("0", 0.0), ("1", 0.1), ("5", 0.5), ("9", 0.9)],
)
def test_numericKeysSeekToVideoFraction(dummyVideo, key, expectedFraction):
  """動画の長さが分かる場合，数字キーが対応する割合へ移動する."""
  player = Player(dummyVideo, PlaybackOptions(), stream=io.StringIO())
  player._duration = 100.0
  movedFractions: list[float] = []
  changedVolumes: list[int] = []
  player._seekToFraction = lambda fraction: movedFractions.append(fraction)
  player._changeVolume = lambda delta: changedVolumes.append(delta)

  assert player._handleKey(key) is True
  assert movedFractions == [expectedFraction]
  assert changedVolumes == []


@pytest.mark.parametrize(
  "key, expectedDelta",
  [("[", -config.VOLUME_STEP), ("]", config.VOLUME_STEP)],
)
def test_bracketKeysChangeVolume(dummyVideo, key, expectedDelta):
  """角括弧キーが数字キーと競合せず音量を変更する."""
  player = Player(dummyVideo, PlaybackOptions(), stream=io.StringIO())
  changedVolumes: list[int] = []
  player._changeVolume = lambda delta: changedVolumes.append(delta)

  assert player._handleKey(key) is True
  assert changedVolumes == [expectedDelta]


def test_numericKeysNeverChangeVolume(dummyVideo):
  """長さが分からない動画でも，数字キーが音量を変えないことを確認する."""
  player = Player(dummyVideo, PlaybackOptions(), stream=io.StringIO())
  player._duration = 0.0
  changedVolumes: list[int] = []
  player._changeVolume = lambda delta: changedVolumes.append(delta)

  for key in ("0", "9"):
    assert player._handleKey(key) is True

  assert changedVolumes == []
  assert "長さが分からない" in player._notice


def test_keyHelpFitsAvailableWidth():
  """操作説明が与えられた幅を超えないことを確認する."""
  from fraterm.player import buildKeyHelp
  from fraterm.textwidth import displayWidth

  for width in range(0, 120, 7):
    for withAudio in (True, False):
      assert displayWidth(buildKeyHelp(width, withAudio)) <= width


def test_keyHelpKeepsImportantKeysWhenNarrow():
  """狭い画面では，終了と一時停止の案内が優先されることを確認する."""
  from fraterm.player import buildKeyHelp

  narrow = buildKeyHelp(30, True)
  assert "[q/Esc]終了" in narrow
  assert "[s]保存" not in narrow


def test_keyHelpHidesAudioKeysWithoutAudio():
  """音声を鳴らしていないときは，音量と消音の案内を出さないことを確認する."""
  from fraterm.player import buildKeyHelp

  helpText = buildKeyHelp(200, False)
  assert "音量" not in helpText
  assert "消音" not in helpText
  assert "[[/]]音量" in buildKeyHelp(200, True)
