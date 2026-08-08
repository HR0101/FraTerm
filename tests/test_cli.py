"""CLIコマンドに関するテスト."""

from __future__ import annotations

import argparse
import sys

import pytest

from fraterm import cli, config, source
from fraterm.registry import Registry

# テストで使用するダミーのURL
SAMPLE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 解決済みの直リンクを模したURL
RESOLVED_URL = "https://example.invalid/stream.mp4"


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


def collectSubcommandNames() -> set[str]:
  """パーサに登録されている全サブコマンド名（別名を含む）を集める."""
  parser = cli.buildParser()
  names: set[str] = set()
  for action in parser._actions:
    if isinstance(action, argparse._SubParsersAction):
      names.update(action.choices.keys())
  return names


def test_allSubcommandsAreReservedNames():
  """サブコマンドを増やしても予約語の更新漏れが起きないことを確認する."""
  from fraterm.registry import RESERVED_NAMES

  missing = collectSubcommandNames() - set(RESERVED_NAMES)
  assert missing == set(), f"予約語に入っていないサブコマンド: {sorted(missing)}"


def test_allSubcommandsAreRecognizedAsCommands():
  """サブコマンドが登録名として誤解釈されないことを確認する."""
  for name in collectSubcommandNames():
    assert cli.expandImplicitPlay([name]) == [name]


@pytest.mark.parametrize("reservedName", ["cache", "CACHE", "ls", "info", "delete"])
def test_reservedNamesCannotBeRegistered(dummyVideo, capsys, reservedName):
  """予約語は大文字小文字を問わず登録できないことを確認する."""
  assert cli.main(["add", reservedName, str(dummyVideo)]) == cli.EXIT_ERROR
  assert "コマンド名と重複" in capsys.readouterr().err


@pytest.mark.parametrize("charset", ["　あい", "あa", "・－"])
def test_wideCharsetIsRejected(dummyVideo, charset):
  """表示幅が1でない文字セットを拒否することを確認する."""
  with pytest.raises(SystemExit) as exitInfo:
    cli.main(["run", str(dummyVideo), "--charset", charset])
  assert exitInfo.value.code != 0


def test_blockCharsetIsStillAccepted(dummyVideo):
  """既存のブロック文字プリセットは引き続き使えることを確認する."""
  cli.main(["add", "sample", str(dummyVideo), "--charset", "blocks"])
  assert Registry().get("sample").charset == "blocks"


def test_controlCharactersAreStrippedFromListing(dummyVideo, tmp_path, capsys):
  """制御文字を含むパスがそのまま端末へ出力されないことを確認する."""
  trickyFile = tmp_path / "movie\x1b[31m.mp4"
  trickyFile.write_bytes(b"\x00")

  cli.main(["add", "tricky", str(trickyFile)])
  capsys.readouterr()

  cli.main(["list"])
  listing = capsys.readouterr().out
  assert "\x1b" not in listing

  cli.main(["show", "tricky"])
  assert "\x1b" not in capsys.readouterr().out


def test_saveHandlerRegistersLocalFile(dummyVideo, recordedPlayers):
  """再生中の保存で，ローカルファイルがそのまま登録されることを確認する."""
  cli.main(["run", str(dummyVideo), "--mode", "edge", "--width", "70"])

  saveHandler = recordedPlayers[0].options.onSave
  message = saveHandler("myclip")

  entry = Registry().get("myclip")
  assert entry.path == str(dummyVideo)
  assert entry.mode == "edge"
  assert entry.width == 70
  assert entry.cache is False
  assert "myclip" in message


def test_saveHandlerRejectsDuplicateName(dummyVideo, recordedPlayers):
  """すでに使われている名前では保存しないことを確認する."""
  cli.main(["add", "myclip", str(dummyVideo)])
  cli.main(["run", str(dummyVideo)])

  message = recordedPlayers[0].options.onSave("myclip")
  assert "すでに登録されています" in message


def test_saveHandlerRejectsInvalidName(dummyVideo, recordedPlayers):
  """使用できない名前を弾くことを確認する."""
  cli.main(["run", str(dummyVideo)])

  message = recordedPlayers[0].options.onSave("list")
  assert "コマンド名と重複" in message
  assert Registry().names() == []


def test_saveHandlerDownloadsUrlForOfflinePlayback(
  tmp_path, monkeypatch, recordedSources, recordedPlayers
):
  """URLの保存でダウンロードし，オフライン再生できる形で登録することを確認する."""
  downloadedFile = tmp_path / "saved.mp4"
  downloadedFile.write_bytes(b"\x00")

  monkeypatch.setattr(cli.source, "fetchMetadata", lambda url, quality, cookies=None: {"id": "abc", "ext": "mp4"})
  monkeypatch.setattr(
    cli.source,
    "downloadToCache",
    lambda url, quality, targetPath, notify=None, cookies=None: downloadedFile,
  )

  cli.main(["run", SAMPLE_URL, "--quality", "360"])
  message = recordedPlayers[0].options.onSave("zoo")

  entry = Registry().get("zoo")
  assert entry.path == SAMPLE_URL  # 元のURLを保持している
  assert entry.cache is True
  assert entry.cachedPath == str(downloadedFile)
  assert entry.quality == "360"
  assert "オフライン" in message


def test_colorOptionIsPersistedAndUsed(dummyVideo, recordedPlayers):
  """文字の着色指定が保存され，再生時に使われることを確認する."""
  cli.main(["add", "sample", str(dummyVideo), "--mode", "ascii", "--color", "256"])
  assert Registry().get("sample").color == "256"

  assert cli.main(["sample"]) == cli.EXIT_OK
  assert recordedPlayers[0].options.color == "256"


def test_colorOptionCanBeOverridden(dummyVideo, recordedPlayers):
  """再生時の着色指定が登録内容より優先されることを確認する."""
  cli.main(["add", "sample", str(dummyVideo), "--color", "256"])
  cli.main(["play", "sample", "--color", "true"])

  assert recordedPlayers[0].options.color == "true"
  assert Registry().get("sample").color == "256"


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


@pytest.fixture
def recordedSources(monkeypatch):
  """URLの解決処理を差し替え，渡された引数を記録できるようにする."""
  calls: list[dict] = []

  def fakeOpenSource(pathOrUrl, quality=None, useCache=False, notify=None, cookies=None):
    calls.append(
      {
        "path": pathOrUrl,
        "quality": quality,
        "cache": useCache,
        "cookies": cookies,
      }
    )
    return source.PlayableSource(
      path=RESOLVED_URL, title="テスト動画", duration=212.0, isRemote=True
    )

  monkeypatch.setattr(cli.source, "openSource", fakeOpenSource)
  return calls


def test_addUrlStoresUrlAsIs(capsys):
  """URLがそのまま登録されることを確認する."""
  assert cli.main(["add", "opening", SAMPLE_URL, "--quality", "720", "--cache"]) == cli.EXIT_OK
  capsys.readouterr()

  entry = Registry().get("opening")
  assert entry.path == SAMPLE_URL
  assert entry.isRemote is True
  assert entry.quality == "720"
  assert entry.cache is True


def test_addUrlWarnsWhenYtdlpMissing(monkeypatch, capsys):
  """yt-dlp が無い場合に登録時点で案内が出ることを確認する."""
  monkeypatch.setattr(cli.source, "isAvailable", lambda: False)

  cli.main(["add", "opening", SAMPLE_URL])
  assert "yt-dlp" in capsys.readouterr().out


def test_showUrlEntryDisplaysUrlSettings(capsys):
  """URL登録の詳細に画質とキャッシュ設定が表示されることを確認する."""
  cli.main(["add", "opening", SAMPLE_URL, "--quality", "360"])
  capsys.readouterr()

  assert cli.main(["show", "opening"]) == cli.EXIT_OK
  output = capsys.readouterr().out
  assert "URL" in output
  assert "360" in output
  assert "直接ストリーミング" in output


def test_playUrlResolvesWithStoredSettings(recordedSources, recordedPlayers):
  """登録したURLが，保存した画質で解決されてから再生されることを確認する."""
  cli.main(["add", "opening", SAMPLE_URL, "--quality", "720"])

  assert cli.main(["opening"]) == cli.EXIT_OK
  assert len(recordedSources) == 1
  assert recordedSources[0]["path"] == SAMPLE_URL
  assert recordedSources[0]["quality"] == "720"
  assert recordedSources[0]["cache"] is False

  played = recordedPlayers[0]
  assert played.videoPath == RESOLVED_URL
  assert played.options.duration == 212.0
  assert played.options.title == "opening"


def test_playUrlOverridesQualityWithoutSaving(recordedSources, recordedPlayers):
  """再生時の画質指定が登録内容へ保存されないことを確認する."""
  cli.main(["add", "opening", SAMPLE_URL, "--quality", "720"])
  cli.main(["play", "opening", "--quality", "360", "--cache"])

  assert recordedSources[0]["quality"] == "360"
  assert recordedSources[0]["cache"] is True
  assert Registry().get("opening").quality == "720"
  assert Registry().get("opening").cache is False


def test_runUrlWithoutRegistration(recordedSources, recordedPlayers):
  """run でURLを直接再生できることを確認する."""
  assert cli.main(["run", SAMPLE_URL, "--mode", "color"]) == cli.EXIT_OK

  assert recordedSources[0]["path"] == SAMPLE_URL
  assert recordedPlayers[0].videoPath == RESOLVED_URL
  # 登録していない場合は動画のタイトルを表示に使う
  assert recordedPlayers[0].options.title == "テスト動画"
  assert Registry().names() == []


def test_editUrlQuality(capsys):
  """edit で画質とキャッシュ設定を変更できることを確認する."""
  cli.main(["add", "opening", SAMPLE_URL])
  capsys.readouterr()

  assert cli.main(["edit", "opening", "--quality", "1080", "--cache"]) == cli.EXIT_OK
  entry = Registry().get("opening")
  assert entry.quality == "1080"
  assert entry.cache is True


def test_cookieSettingsArePersistedAndUsed(recordedSources, recordedPlayers, capsys):
  """Cookieの指定が登録され，再生時に使われることを確認する."""
  cli.main(["add", "restricted", SAMPLE_URL, "--cookies-from-browser", "chrome"])
  capsys.readouterr()

  assert Registry().get("restricted").cookiesFromBrowser == "chrome"

  assert cli.main(["restricted"]) == cli.EXIT_OK
  assert recordedSources[0]["cookies"].fromBrowser == "chrome"


def test_cookieOverrideAtPlaytime(recordedSources, recordedPlayers):
  """再生時のCookie指定が登録内容より優先されることを確認する."""
  cli.main(["add", "restricted", SAMPLE_URL, "--cookies-from-browser", "chrome"])
  cli.main(["play", "restricted", "--cookies-from-browser", "safari"])

  assert recordedSources[0]["cookies"].fromBrowser == "safari"
  assert Registry().get("restricted").cookiesFromBrowser == "chrome"


def test_showDisplaysCookieSetting(capsys):
  """詳細表示にCookieの設定が現れることを確認する."""
  cli.main(["add", "restricted", SAMPLE_URL, "--cookies-from-browser", "firefox"])
  capsys.readouterr()

  cli.main(["show", "restricted"])
  output = capsys.readouterr().out
  assert "Cookie" in output
  assert "firefox" in output


def test_playerClientIsPersistedAndUsed(recordedSources, recordedPlayers, capsys):
  """取得方法の指定が登録され，再生時に使われることを確認する."""
  cli.main(["add", "restricted", SAMPLE_URL, "--player-client", "mweb"])
  capsys.readouterr()

  assert Registry().get("restricted").playerClient == "mweb"

  assert cli.main(["restricted"]) == cli.EXIT_OK
  assert recordedSources[0]["cookies"].playerClient == "mweb"


def test_unsupportedBrowserIsRejected(capsys):
  """対応していないブラウザ名が拒否されることを確認する."""
  with pytest.raises(SystemExit) as exitInfo:
    cli.main(["run", SAMPLE_URL, "--cookies-from-browser", "netscape"])
  assert exitInfo.value.code != 0


def test_browserProfileSpecIsAccepted(recordedSources, recordedPlayers):
  """プロファイル付きのブラウザ指定を受け付けることを確認する."""
  assert cli.main(["run", SAMPLE_URL, "--cookies-from-browser", "chrome:Profile 1"]) == cli.EXIT_OK
  assert recordedSources[0]["cookies"].fromBrowser == "chrome:Profile 1"


def test_cachedFileIsReusedWithoutNetwork(
  tmp_path, monkeypatch, recordedSources, recordedPlayers
):
  """ダウンロード済みなら，URLを解決せずに再生することを確認する."""
  cachedFile = tmp_path / "cached.mp4"
  cachedFile.write_bytes(b"\x00")

  cli.main(["add", "opening", SAMPLE_URL, "--cache"])
  Registry().update("opening", {"cachedPath": str(cachedFile)})

  assert cli.main(["opening"]) == cli.EXIT_OK
  assert recordedSources == []  # ネットワーク処理を呼んでいない
  assert recordedPlayers[0].videoPath == str(cachedFile)


def test_downloadedPathIsRemembered(tmp_path, monkeypatch, recordedPlayers):
  """ダウンロードした保存先が登録内容へ記録されることを確認する."""
  downloadedFile = tmp_path / "downloaded.mp4"
  downloadedFile.write_bytes(b"\x00")

  def fakeOpenSource(pathOrUrl, quality=None, useCache=False, notify=None, cookies=None):
    return source.PlayableSource(
      path=str(downloadedFile), title="テスト動画", duration=10.0, isRemote=False
    )

  monkeypatch.setattr(cli.source, "openSource", fakeOpenSource)

  cli.main(["add", "opening", SAMPLE_URL, "--cache"])
  assert cli.main(["opening"]) == cli.EXIT_OK

  assert Registry().get("opening").cachedPath == str(downloadedFile)


def test_cacheIsNotReusedAfterQualityChange(
  tmp_path, recordedSources, recordedPlayers, capsys
):
  """画質を変えたら，前の画質のキャッシュを使い回さないことを確認する."""
  cachedFile = tmp_path / "cached480.mp4"
  cachedFile.write_bytes(b"\x00")

  cli.main(["add", "opening", SAMPLE_URL, "--cache", "--quality", "480"])
  Registry().update(
    "opening", {"cachedPath": str(cachedFile), "cachedQuality": "480"}
  )
  capsys.readouterr()

  # 同じ画質ならキャッシュをそのまま使う
  assert cli.main(["opening"]) == cli.EXIT_OK
  assert recordedSources == []
  assert recordedPlayers[0].videoPath == str(cachedFile)

  # 画質を変えたら取得し直す
  assert cli.main(["play", "opening", "--quality", "720"]) == cli.EXIT_OK
  assert len(recordedSources) == 1
  assert recordedSources[0]["quality"] == "720"


def test_cachedQualityIsRecordedAfterDownload(tmp_path, monkeypatch, recordedPlayers):
  """ダウンロード時に，使用した画質も登録内容へ残ることを確認する."""
  downloadedFile = tmp_path / "downloaded.mp4"
  downloadedFile.write_bytes(b"\x00")

  monkeypatch.setattr(
    cli.source,
    "openSource",
    lambda pathOrUrl, quality=None, useCache=False, notify=None, cookies=None: source.PlayableSource(
      path=str(downloadedFile), title="テスト動画", isRemote=False
    ),
  )

  cli.main(["add", "opening", SAMPLE_URL, "--cache", "--quality", "720"])
  cli.main(["opening"])

  entry = Registry().get("opening")
  assert entry.cachedPath == str(downloadedFile)
  assert entry.cachedQuality == "720"


def test_missingCachedFileFallsBackToResolve(recordedSources, recordedPlayers):
  """保存先のファイルが消えていれば，改めて解決し直すことを確認する."""
  cli.main(["add", "opening", SAMPLE_URL, "--cache"])
  Registry().update("opening", {"cachedPath": "/存在しない/場所/video.mp4"})

  assert cli.main(["opening"]) == cli.EXIT_OK
  assert len(recordedSources) == 1
  assert recordedPlayers[0].videoPath == RESOLVED_URL


def test_cacheCommandListsAndClears(isolatedHome, capsys):
  """cache コマンドで一覧表示と削除ができることを確認する."""
  cacheDirectory = isolatedHome / config.CACHE_DIR_NAME
  cacheDirectory.mkdir(parents=True, exist_ok=True)
  (cacheDirectory / "video.mp4").write_bytes(b"\x00" * 2048)

  assert cli.main(["cache"]) == cli.EXIT_OK
  listing = capsys.readouterr().out
  assert "video.mp4" in listing
  assert "2.0 KB" in listing

  assert cli.main(["cache", "--clear"]) == cli.EXIT_OK
  assert "1件" in capsys.readouterr().out
  assert list(cacheDirectory.iterdir()) == []


def test_cacheCommandWithoutFiles(capsys):
  """キャッシュが無い場合の表示を確認する."""
  assert cli.main(["cache"]) == cli.EXIT_OK
  assert "キャッシュはありません" in capsys.readouterr().out


@pytest.mark.parametrize(
  "sizeInBytes, expected",
  [(512, "512 B"), (2048, "2.0 KB"), (5 * 1024 * 1024, "5.0 MB")],
)
def test_formatBytes(sizeInBytes, expected):
  """バイト数が読みやすい単位へ変換されることを確認する."""
  assert cli.formatBytes(sizeInBytes) == expected


@pytest.mark.parametrize(
  "invokedPath, expected",
  [
    ("/usr/local/bin/fraterm", "fraterm"),
    ("/Users/me/.local/bin/ft", "ft"),
    ("/path/to/fraterm/__main__.py", "fraterm"),
    ("", "fraterm"),
  ],
)
def test_commandNameFollowsInvocation(monkeypatch, invokedPath, expected):
  """打たれたコマンド名が表示に反映されることを確認する."""
  monkeypatch.setattr(sys, "argv", [invokedPath])
  assert config.commandName() == expected


def test_helpUsesShortCommandName(monkeypatch, capsys):
  """短い名前で起動した場合，ヘルプの表示もその名前になることを確認する."""
  monkeypatch.setattr(sys, "argv", ["/Users/me/.local/bin/ft"])

  cli.main([])
  output = capsys.readouterr().out
  assert "usage: ft" in output
  assert "ft add badapple" in output


def test_errorHintUsesShortCommandName(monkeypatch, capsys):
  """エラー時の案内も打たれたコマンド名になることを確認する."""
  monkeypatch.setattr(sys, "argv", ["/Users/me/.local/bin/ft"])

  assert cli.main(["play", "neko"]) == cli.EXIT_ERROR
  assert "`ft list`" in capsys.readouterr().err


def test_versionOption(capsys):
  """--version がバージョンを表示することを確認する."""
  with pytest.raises(SystemExit) as exitInfo:
    cli.main(["--version"])
  assert exitInfo.value.code == 0
  assert config.VERSION in capsys.readouterr().out
