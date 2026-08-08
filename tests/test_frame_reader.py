"""動画フレーム先読みのテスト."""

from __future__ import annotations

from fraterm.frame_reader import FrameReader


class FakeCapture:
  """少数の整数フレームを返すVideoCapture風オブジェクト."""

  def __init__(self, frameCount: int) -> None:
    self.frames = list(range(frameCount))
    self.position = 0

  def read(self):
    if self.position >= len(self.frames):
      return False, None
    frame = self.frames[self.position]
    self.position += 1
    return True, frame

  def set(self, propertyId: int, value: int) -> bool:
    self.position = int(value)
    return True


def test_frameReaderPrefetchesInOrder():
  """先読みしてもフレーム番号の順序が保たれることを確認する."""
  reader = FrameReader(FakeCapture(5), bufferSize=2)
  try:
    packets = [reader.read() for _ in range(5)]
  finally:
    reader.close()

  assert packets == [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)]
  assert reader.read() is None


def test_frameReaderSeekDropsOldPrefetchedFrames():
  """シーク時に移動前のキューが再生へ混ざらないことを確認する."""
  capture = FakeCapture(8)
  reader = FrameReader(capture, bufferSize=4)
  try:
    reader.seek(1, 5)
    packet = reader.read()
  finally:
    reader.close()

  assert packet == (5, 5)
