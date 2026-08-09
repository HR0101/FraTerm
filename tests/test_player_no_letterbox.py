"""再生時に動画の画角を変更しないことを確認するテスト."""

from __future__ import annotations

import io

import numpy as np

from fraterm.player import PlaybackOptions, Player


def test_renderFrameContentKeepsOriginalFrameBounds(monkeypatch):
  """黒い上下端があっても，描画へ渡すフレームを切り取らない."""
  frame = np.full((100, 200, 3), 180, dtype=np.uint8)
  frame[:20] = 0
  frame[-20:] = 0
  capturedShape: list[tuple[int, ...]] = []

  def fakeRender(frameToRender, *args):
    capturedShape.append(frameToRender.shape)
    return ""

  from fraterm import renderer

  monkeypatch.setattr(renderer, "renderFrame", fakeRender)
  player = Player("dummy.mp4", PlaybackOptions(), stream=io.StringIO())

  player._renderFrameContent(frame, terminalWidth=80, terminalHeight=24)

  assert capturedShape == [frame.shape]
