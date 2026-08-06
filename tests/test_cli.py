"""CLIコマンドに関するテスト."""

from __future__ import annotations

import pytest

from fraterm import cli, config
from fraterm.registry import Registry


class RecordingPlayer:
  """実際には再生せず，渡された引数だけを記録するテスト用のプレイヤー."""

  instances: list["RecordingPlayer"] = []

  def __init__(self, videoPath, options=None, stream=None):
    self.videoPath = videoPath
    self.options = options
    self.played = False
    RecordingPlayer.instances.append(self)

  def play(self) -> None:
    self.played = True


@pytest.fixture
def recordedPlayers(monkeypatch):
  """Player を差し替え，再生要求を記録できるようにする."""
  from fraterm import player as playerModule

  RecordingPlayer.instances = []
  monkeypatch.setattr(playerModule, "Player", RecordingPlayer)
  return RecordingPlayer.instances


def test_noArgumentsShowsHelp(capsys):
  """引数なしで実行するとヘルプが表示されることを確認する."""
  exitCode = cli.main([])
  output = capsys.readouterr().out

  assert exitCode == cli.EXIT_OK
  assert config.APP_NAME in output


def test_addAndListFlow(dummyVideo, capsys):
  """登録してから一覧に表示されることを確認する."""
  assert cli.main(["add", "sample", str(dummyVideo), "--mode", "color"]) == cli.EXIT_OK
  capsys.readouterr()

  assert cli.main(["list"]) == cli.EXIT_OK
  output = capsys.readouterr().out
  assert "sample" in output
  assert "color" in output
  assert str(dummyVideo) in output


def test_listWithoutEntries(capsys):
  """登録が無い場合に案内が表示されることを確認する."""
  assert cli.main(["list"]) == cli.EXIT_OK
  assert "登録されている動画はありません" in capsys.readouterr().out


def test_showDisplaysDetails(dummyVideo, capsys):
  """show が登録内容の詳細を表示することを確認する."""
  cli.main(["add", "sample", str(dummyVideo), "--width", "100", "--audio"])
  capsys.readouterr()

  assert cli.main(["show", "sample"]) == cli.EXIT_OK
  output = capsys.readouterr().out
  assert "登録名" in output
  assert "100 桁" in output
  assert "再生する" in output


def test_removeFlow(dummyVideo, capsys):
  """remove で登録が削除され，動画ファイルは残ることを確認する."""
  cli.main(["add", "sample", str(dummyVideo)])
  capsys.readouterr()

  assert cli.main(["remove", "sample"]) == cli.EXIT_OK
  assert Registry().names() == []
  assert dummyVideo.exists()


def test_unknownNameShowsFriendlyError(capsys):
  """未登録の名前を再生しようとした場合のエラーを確認する."""
  exitCode = cli.main(["play", "neko"])
  errorOutput = capsys.readouterr().err

  assert exitCode == cli.EXIT_ERROR
  assert "「neko」は登録されていません" in errorOutput
  assert f"{config.APP_NAME} list" in errorOutput


def test_duplicateNameRequiresForce(dummyVideo, capsys):
  """同名登録が拒否され，--force で上書きできることを確認する."""
  cli.main(["add", "sample", str(dummyVideo), "--mode", "ascii"])
  capsys.readouterr()

  assert cli.main(["add", "sample", str(dummyVideo), "--mode", "color"]) == cli.EXIT_ERROR
  assert "すでに登録されています" in capsys.readouterr().err

  assert (
    cli.main(["add", "sample", str(dummyVideo), "--mode", "color", "--force"])
    == cli.EXIT_OK
  )
  assert Registry().get("sample").mode == "color"


def test_invalidNameShowsError(dummyVideo, capsys):
  """コマンド名と重複する登録名が拒否されることを確認する."""
  assert cli.main(["add", "list", str(dummyVideo)]) == cli.EXIT_ERROR
  assert "コマンド名と重複" in capsys.readouterr().err


def test_missingVideoShowsError(tmp_path, capsys):
  """存在しない動画を登録しようとした場合のエラーを確認する."""
  assert cli.main(["add", "sample", str(tmp_path / "none.mp4")]) == cli.EXIT_ERROR
  assert "動画ファイルが見つかりません" in capsys.readouterr().err


def test_editUpdatesSettings(dummyVideo, capsys):
  """edit が登録内容を変更することを確認する."""
  cli.main(["add", "sample", str(dummyVideo), "--mode", "ascii"])
  capsys.readouterr()

  assert cli.main(["edit", "sample", "--mode", "color", "--audio"]) == cli.EXIT_OK
  entry = Registry().get("sample")
  assert entry.mode == "color"
  assert entry.audio is True


def test_editWithoutChangesShowsError(dummyVideo, capsys):
  """変更内容を指定しない edit がエラーになることを確認する."""
  cli.main(["add", "sample", str(dummyVideo)])
  capsys.readouterr()

  assert cli.main(["edit", "sample"]) == cli.EXIT_ERROR
  assert "変更する項目" in capsys.readouterr().err


def test_editCanResetWidthToAuto(dummyVideo):
  """--width auto で自動幅へ戻せることを確認する."""
  cli.main(["add", "sample", str(dummyVideo), "--width", "80"])
  cli.main(["edit", "sample", "--width", "auto"])
  assert Registry().get("sample").width is None


def test_playUsesRegisteredSettings(dummyVideo, recordedPlayers):
  """登録した設定が再生時に使われることを確認する."""
  cli.main(["add", "sample", str(dummyVideo), "--mode", "color", "--width", "120"])

  assert cli.main(["play", "sample"]) == cli.EXIT_OK
  assert len(recordedPlayers) == 1

  played = recordedPlayers[0]
  assert played.videoPath == str(dummyVideo)
  assert played.options.mode == "color"
  assert played.options.width == 120
  assert played.options.title == "sample"
  assert played.played is True


def test_implicitPlayByName(dummyVideo, recordedPlayers):
  """登録名だけの指定で再生できることを確認する."""
  cli.main(["add", "sample", str(dummyVideo)])

  assert cli.main(["sample"]) == cli.EXIT_OK
  assert len(recordedPlayers) == 1
  assert recordedPlayers[0].videoPath == str(dummyVideo)


def test_playOverridesAreNotPersisted(dummyVideo, recordedPlayers):
  """再生時のオプションが登録内容へ保存されないことを確認する."""
  cli.main(["add", "sample", str(dummyVideo), "--mode", "ascii"])
  cli.main(["play", "sample", "--mode", "color", "--no-status"])

  assert recordedPlayers[0].options.mode == "color"
  assert recordedPlayers[0].options.showStatus is False
  assert Registry().get("sample").mode == "ascii"


def test_playMissingFileShowsError(tmp_path, capsys, recordedPlayers):
  """登録後に動画ファイルが移動された場合のエラーを確認する."""
  videoFile = tmp_path / "movie.mp4"
  videoFile.write_bytes(b"\x00")
  cli.main(["add", "sample", str(videoFile)])
  capsys.readouterr()
  videoFile.unlink()

  assert cli.main(["sample"]) == cli.EXIT_ERROR
  errorOutput = capsys.readouterr().err
  assert "見つかりません" in errorOutput
  assert recordedPlayers == []


def test_runPlaysWithoutRegistration(dummyVideo, recordedPlayers):
  """run が登録せずに再生することを確認する."""
  assert cli.main(["run", str(dummyVideo), "--mode", "mono"]) == cli.EXIT_OK

  assert recordedPlayers[0].options.mode == "mono"
  assert recordedPlayers[0].options.title == dummyVideo.name
  assert Registry().names() == []


def test_charsetPresetIsAccepted(dummyVideo):
  """文字セットのプリセット名を登録できることを確認する."""
  cli.main(["add", "sample", str(dummyVideo), "--charset", "simple"])
  assert Registry().get("sample").charset == "simple"


def test_invalidOptionValueExits(dummyVideo, capsys):
  """不正なオプション値が argparse のエラーになることを確認する."""
  with pytest.raises(SystemExit) as exitInfo:
    cli.main(["add", "sample", str(dummyVideo), "--width", "0"])
  assert exitInfo.value.code != 0


@pytest.mark.parametrize(
  "rawArgs, expected",
  [
    (["neko"], ["play", "neko"]),
    (["play", "neko"], ["play", "neko"]),
    (["list"], ["list"]),
    (["--version"], ["--version"]),
    ([], []),
  ],
)
def test_expandImplicitPlay(rawArgs, expected):
  """登録名の省略記法が正しく展開されることを確認する."""
  assert cli.expandImplicitPlay(rawArgs) == expected


def test_versionOption(capsys):
  """--version がバージョンを表示することを確認する."""
  with pytest.raises(SystemExit) as exitInfo:
    cli.main(["--version"])
  assert exitInfo.value.code == 0
  assert config.VERSION in capsys.readouterr().out
