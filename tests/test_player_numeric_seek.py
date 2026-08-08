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
