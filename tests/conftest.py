"""テスト全体で共有するフィクスチャを定義するモジュール."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fraterm import config

# テスト用に生成する動画の仕様
SAMPLE_WIDTH = 64
SAMPLE_HEIGHT = 48
SAMPLE_FPS = 10.0
SAMPLE_FRAME_COUNT = 10


@pytest.fixture(autouse=True)
def isolatedHome(tmp_path, monkeypatch):
  """設定ファイルの保存先を一時ディレクトリへ隔離する."""
  monkeypatch.setenv(config.HOME_ENV_VAR, str(tmp_path / "fraterm-home"))
  return tmp_path / "fraterm-home"


@pytest.fixture
def sampleVideo(tmp_path) -> Path:
  """テスト用の短い動画ファイルを生成して返す."""
  import cv2

  videoPath = tmp_path / "sample.avi"
  writer = cv2.VideoWriter(
    str(videoPath),
    cv2.VideoWriter_fourcc(*"MJPG"),
    SAMPLE_FPS,
    (SAMPLE_WIDTH, SAMPLE_HEIGHT),
  )
  assert writer.isOpened(), "テスト用動画を作成できません（コーデック未対応）"

  for frameIndex in range(SAMPLE_FRAME_COUNT):
    frame = np.full(
      (SAMPLE_HEIGHT, SAMPLE_WIDTH, 3),
      frameIndex * 25 % 256,
      dtype=np.uint8,
    )
    writer.write(frame)
  writer.release()

  return videoPath


@pytest.fixture
def dummyVideo(tmp_path) -> Path:
  """再生しない用途向けの，中身が空のダミー動画ファイルを返す."""
  videoPath = tmp_path / "dummy.mp4"
  videoPath.write_bytes(b"\x00")
  return videoPath
