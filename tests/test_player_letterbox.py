"""再生開始前の黒帯スキャンのテスト."""

from __future__ import annotations

import numpy as np

from fraterm.player import Player


class FakeCapture:
  """フレーム列をシークできるVideoCapture風オブジェクト."""

  def __init__(self, frames: list[np.ndarray]) -> None:
    self.frames = frames
    self.position = 0

  def get(self, propertyId: int) -> int:
    return len(self.frames)

  def set(self, propertyId: int, value: int) -> bool:
    self.position = int(value)
    return True

  def read(self):
    if self.position >= len(self.frames):
      return False, None
    frame = self.frames[self.position]
    self.position += 1
    return True, frame


class FakeCv2:
  CAP_PROP_FRAME_COUNT = 7
  CAP_PROP_POS_FRAMES = 1


def letterboxedFrame(
  top: int = 10,
  bottom: int = 10,
  left: int = 20,
  right: int = 20,
) -> np.ndarray:
  """黒帯付きの固定サイズフレームを作る."""
  frame = np.full((100, 200, 3), 180, dtype=np.uint8)
  if top > 0:
    frame[:top] = 0
  if bottom > 0:
    frame[-bottom:] = 0
  if left > 0:
    frame[:, :left] = 0
  if right > 0:
    frame[:, -right:] = 0
  return frame


def test_scanPersistentBordersRequiresEverySampleToAgree():
  """一部の時点で帯が消える場合は，その辺をクロップしないことを確認する."""
  frames = [letterboxedFrame() for _ in range(12)]
  frames[6] = letterboxedFrame(bottom=0)

  bounds = Player._scanPersistentBorders(FakeCapture(frames), FakeCv2)

  assert bounds == (10, 100, 20, 180)


def test_scanPersistentBordersReturnsNoneForUnseekableMetadata():
  """フレーム数を取得できない入力では安全側に倒すことを確認する."""
  capture = FakeCapture([letterboxedFrame()] * 3)
  capture.get = lambda propertyId: 0

  assert Player._scanPersistentBorders(capture, FakeCv2) is None
