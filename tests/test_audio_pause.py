"""音声プロセスの即時停止と再開競合に関するテスト."""

from __future__ import annotations

import pytest

from fraterm import audio


class FakeProcess:
  """終了方法だけを記録するPopen代替."""

  def __init__(self) -> None:
    self.killCount = 0
    self.terminateCount = 0
    self.stderr = None

  def poll(self):
    return None

  def kill(self) -> None:
    self.killCount += 1

  def terminate(self) -> None:
    self.terminateCount += 1

  def wait(self, timeout: float | None = None) -> int:
    return 0


def test_audioStopKillsProcessImmediately():
  """一時停止時にffplayの終了待ちをせず，直ちに音を止める."""
  player = audio.AudioPlayer("sample.mp4")
  process = FakeProcess()
  player._process = process

  player.stop()

  assert process.killCount == 1
  assert process.terminateCount == 0


def test_staleAudioStatusCannotWakeNewPlayback():
  """停止済みffplayの遅れた進捗を，新しい再生位置として扱わない."""
  player = audio.AudioPlayer("sample.mp4")
  oldProcess = FakeProcess()
  newProcess = FakeProcess()
  player._process = newProcess
  player._readyEvent.clear()

  player._recordStatus(oldProcess, "12.0 M-A: 0.0")
  assert player._readyEvent.is_set() is False
  assert player._lastAudioPosition is None

  player._recordStatus(newProcess, "3.0 M-A: 0.0")
  assert player._readyEvent.is_set() is True
  assert player._lastAudioPosition == 3.0

  player._process = None


def test_startupCompensationUsesMeasuredDelay(monkeypatch):
  """絶対時刻形式の進捗から，次回再開の補正量を求める."""
  player = audio.AudioPlayer("sample.mp4")
  process = FakeProcess()
  player._process = process
  player._processStartedAt = 9.8
  player._requestedPosition = 10.0
  monkeypatch.setattr(audio.time, "perf_counter", lambda: 10.0)

  player._recordStatus(process, "9.98 M-A: 0.0")

  assert player.startupCompensation(1.0) == pytest.approx(0.22)
  assert player.currentPosition() == pytest.approx(9.98)
  player._process = None


def test_relativeAudioStatusIsNormalizedToRequestedPosition(monkeypatch):
  """シーク位置を0秒とするMP4の進捗を，動画全体の時刻へ直す."""
  player = audio.AudioPlayer("sample.mp4")
  process = FakeProcess()
  player._process = process
  player._processStartedAt = 9.8
  player._requestedPosition = 10.0
  monkeypatch.setattr(audio.time, "perf_counter", lambda: 10.0)

  player._recordStatus(process, "-0.02 M-A: 0.0")

  assert player.startupCompensation(1.0) == pytest.approx(0.22)
  assert player.currentPosition() == pytest.approx(9.98)

  player._recordStatus(process, "0.48 M-A: 0.0")
  assert player.currentPosition() == pytest.approx(10.48)
  player._process = None
