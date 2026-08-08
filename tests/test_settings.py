"""オプションの既定値の保存に関するテスト."""

from __future__ import annotations

import json

import pytest

from fraterm import cli, config, settings
from fraterm.errors import RegistryError
from fraterm.registry import Registry


def test_loadWithoutFile():
  """設定ファイルが無い場合は空の辞書を返すことを確認する."""
  assert settings.load() == {}


def test_saveAndLoadRoundTrip(isolatedHome):
  """保存した既定値をそのまま読み戻せることを確認する."""
  settings.save({"mode": "edge", "color": "256", "width": 100})

  values = settings.load()
  assert values == {"mode": "edge", "color": "256", "width": 100}
  assert (isolatedHome / config.SETTINGS_FILE_NAME).is_file()


def test_updateMergesValues():
  """update が既存の設定を残したまま追記することを確認する."""
  settings.save({"mode": "edge"})
  values = settings.update({"color": "true"})

  assert values == {"mode": "edge", "color": "true"}


def test_clearRemovesFile(isolatedHome):
  """clear で設定ファイルが消えることを確認する."""
  settings.save({"mode": "edge"})
  settings.clear()

  assert settings.load() == {}
  assert not (isolatedHome / config.SETTINGS_FILE_NAME).exists()


def test_unknownAndInvalidKeysAreIgnored(isolatedHome):
  """未知の項目や不正な値は読み込み時に捨てることを確認する."""
  isolatedHome.mkdir(parents=True, exist_ok=True)
  (isolatedHome / config.SETTINGS_FILE_NAME).write_text(
    json.dumps({"mode": "hologram", "unknownKey": 1, "color": "256"}),
    encoding="utf-8",
  )

  assert settings.load() == {"color": "256"}


def test_brokenFileRaisesWithHint(isolatedHome):
  """壊れた設定ファイルに対して初期化方法を案内することを確認する."""
  isolatedHome.mkdir(parents=True, exist_ok=True)
  (isolatedHome / config.SETTINGS_FILE_NAME).write_text("{ broken", encoding="utf-8")

  with pytest.raises(RegistryError) as errorInfo:
    settings.load()
  assert "defaults --clear" in (errorInfo.value.hint or "")


def test_defaultsCommandShowsAndSaves(capsys):
  """defaults コマンドで既定値を設定・表示できることを確認する."""
  assert cli.main(["defaults", "-m", "edge", "-c", "256"]) == cli.EXIT_OK
  output = capsys.readouterr().out
  assert "既定値を保存しました" in output
  assert "edge" in output

  assert cli.main(["defaults"]) == cli.EXIT_OK
  assert "edge" in capsys.readouterr().out


def test_defaultsCommandClears(capsys):
  """--clear で既定値を削除できることを確認する."""
  cli.main(["defaults", "-m", "edge"])
  capsys.readouterr()

  assert cli.main(["defaults", "--clear"]) == cli.EXIT_OK
  assert "削除しました" in capsys.readouterr().out
  assert settings.load() == {}


def test_defaultsAliasConfig(capsys):
  """config という別名でも呼べることを確認する."""
  assert cli.main(["config", "-m", "mono"]) == cli.EXIT_OK
  assert settings.load()["mode"] == "mono"


def test_defaultsApplyToRun(dummyVideo, recordedPlayers):
  """既定値が run へ反映されることを確認する."""
  cli.main(["defaults", "-m", "edge", "-c", "256", "-w", "70"])

  assert cli.main(["run", str(dummyVideo)]) == cli.EXIT_OK
  options = recordedPlayers[0].options
  assert options.mode == "edge"
  assert options.color == "256"
  assert options.width == 70


def test_preRenderDefaultAppliesToRun(dummyVideo, recordedPlayers):
  """事前生成の既定値が run の再生設定へ反映されることを確認する."""
  cli.main(["defaults", "--pre-render"])

  assert cli.main(["run", str(dummyVideo)]) == cli.EXIT_OK
  assert recordedPlayers[0].options.preRender is True


def test_commandLineOverridesDefaults(dummyVideo, recordedPlayers):
  """コマンドで指定した値が既定値より優先されることを確認する."""
  cli.main(["defaults", "-m", "edge", "-c", "256"])

  cli.main(["run", str(dummyVideo), "-m", "ascii"])
  options = recordedPlayers[0].options
  assert options.mode == "ascii"  # 明示した指定が勝つ
  assert options.color == "256"  # 指定しなかった項目は既定値のまま


def test_defaultsApplyToAdd(dummyVideo):
  """既定値が add の登録内容へ反映されることを確認する."""
  cli.main(["defaults", "-m", "edge", "-s", "detailed", "-q", "720"])
  cli.main(["add", "sample", str(dummyVideo)])

  entry = Registry().get("sample")
  assert entry.mode == "edge"
  assert entry.charset == "detailed"
  assert entry.quality == "720"


def test_defaultsDoNotOverrideRegisteredEntry(dummyVideo, recordedPlayers):
  """登録済みの設定は，後から変えた既定値に上書きされないことを確認する."""
  cli.main(["add", "sample", str(dummyVideo), "-m", "ascii"])
  cli.main(["defaults", "-m", "mono"])

  cli.main(["sample"])
  assert recordedPlayers[0].options.mode == "ascii"


@pytest.fixture
def recordedPlayers(monkeypatch):
  """Player を差し替え，再生要求を記録できるようにする."""
  from fraterm import player as playerModule

  instances: list = []

  class RecordingPlayer:
    def __init__(self, videoPath, options=None, stream=None):
      self.videoPath = videoPath
      self.options = options
      instances.append(self)

    def play(self) -> None:
      return None

  monkeypatch.setattr(playerModule, "Player", RecordingPlayer)
  return instances
