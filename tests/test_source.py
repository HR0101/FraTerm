"""URLの解決とキャッシュに関するテスト."""

from __future__ import annotations

import json
import subprocess
import types

import pytest

from fraterm import config, source
from fraterm.errors import SourceError, VideoFileError

# テストで使用するダミーのURL
SAMPLE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# yt-dlp の応答を模した動画情報
SAMPLE_METADATA = {
  "id": "dQw4w9WgXcQ",
  "ext": "mp4",
  "title": "テスト動画",
  "duration": 212,
  "url": "https://example.invalid/stream.mp4",
}


def makeCompletedProcess(stdout: str = "", stderr: str = "", returncode: int = 0):
  """subprocess.run の戻り値を模したオブジェクトを作る."""
  return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


@pytest.mark.parametrize(
  "text, expected",
  [
    ("https://www.youtube.com/watch?v=abc", True),
    ("http://example.com/movie.mp4", True),
    ("  https://example.com/movie.mp4  ", True),
    ("/Users/me/Videos/movie.mp4", False),
    ("movie.mp4", False),
    ("", False),
  ],
)
def test_isUrl(text, expected):
  """URLとファイルパスを判別できることを確認する."""
  assert source.isUrl(text) is expected


@pytest.mark.parametrize("quality", ["360", "480", "720", "1080", "best", "worst"])
def test_formatSelectorAcceptsAllChoices(quality):
  """指定できる画質すべてがフォーマット指定へ変換できることを確認する."""
  selector = source.formatSelector(quality)
  assert selector
  # 映像と音声が一体の形式を優先している
  assert "[vcodec!=none][acodec!=none]" in selector


def test_formatSelectorUsesHeightLimit():
  """数値の画質が高さの上限として反映されることを確認する."""
  assert "[height<=480]" in source.formatSelector("480")
  assert "[height<=720]" in source.formatSelector("720p")


def test_formatSelectorDefaultsToConfig():
  """画質を指定しない場合は既定値が使われることを確認する."""
  assert source.formatSelector(None) == source.formatSelector(config.DEFAULT_QUALITY)


def test_formatSelectorRejectsInvalidQuality():
  """不正な画質指定がエラーになることを確認する."""
  with pytest.raises(SourceError):
    source.formatSelector("ultra")


def test_ytdlpCommandRaisesWhenMissing(monkeypatch):
  """yt-dlp が見つからない場合に導入方法を示すエラーになることを確認する."""
  monkeypatch.setattr(source.shutil, "which", lambda name: None)
  monkeypatch.setattr(source.importlib.util, "find_spec", lambda name: None)

  with pytest.raises(SourceError) as errorInfo:
    source.ytdlpCommand()
  assert "yt-dlp" in errorInfo.value.message
  assert "pip install" in (errorInfo.value.hint or "")


def test_ytdlpCommandFallsBackToModule(monkeypatch):
  """コマンドが無くてもモジュールがあれば実行できることを確認する."""
  monkeypatch.setattr(source.shutil, "which", lambda name: None)
  monkeypatch.setattr(source.importlib.util, "find_spec", lambda name: object())

  command = source.ytdlpCommand()
  assert command[1:] == ["-m", "yt_dlp"]


def test_runYtdlpRaisesOnFailure(monkeypatch):
  """yt-dlp が失敗した場合にエラー内容が伝わることを確認する."""
  monkeypatch.setattr(source, "ytdlpCommand", lambda: ["yt-dlp"])
  monkeypatch.setattr(
    source.subprocess,
    "run",
    lambda *args, **kwargs: makeCompletedProcess(
      stderr="ERROR: Video unavailable", returncode=1
    ),
  )

  with pytest.raises(SourceError) as errorInfo:
    source.runYtdlp(["-J", SAMPLE_URL], 10)
  assert "Video unavailable" in errorInfo.value.message


def test_runYtdlpRaisesOnTimeout(monkeypatch):
  """yt-dlp の応答が無い場合にタイムアウトのエラーになることを確認する."""
  def raiseTimeout(*args, **kwargs):
    raise subprocess.TimeoutExpired(cmd="yt-dlp", timeout=10)

  monkeypatch.setattr(source, "ytdlpCommand", lambda: ["yt-dlp"])
  monkeypatch.setattr(source.subprocess, "run", raiseTimeout)

  with pytest.raises(SourceError) as errorInfo:
    source.runYtdlp(["-J", SAMPLE_URL], 10)
  assert "タイムアウト" in errorInfo.value.message


def test_fetchMetadataParsesJson(monkeypatch):
  """yt-dlp のJSON出力を解釈できることを確認する."""
  monkeypatch.setattr(
    source,
    "runYtdlp",
    lambda arguments, timeout: makeCompletedProcess(stdout=json.dumps(SAMPLE_METADATA)),
  )

  metadata = source.fetchMetadata(SAMPLE_URL, "480")
  assert metadata["title"] == "テスト動画"


def test_fetchMetadataRejectsBrokenJson(monkeypatch):
  """壊れた応答に対してエラーになることを確認する."""
  monkeypatch.setattr(
    source, "runYtdlp", lambda arguments, timeout: makeCompletedProcess(stdout="broken")
  )

  with pytest.raises(SourceError):
    source.fetchMetadata(SAMPLE_URL, None)


def test_extractStreamUrlFromTopLevel():
  """動画情報の url から直接再生URLを取り出せることを確認する."""
  assert source.extractStreamUrl(SAMPLE_METADATA) == SAMPLE_METADATA["url"]


def test_extractStreamUrlFromRequestedDownloads():
  """requested_downloads からもURLを取り出せることを確認する."""
  metadata = {"requested_downloads": [{"url": "https://example.invalid/other.mp4"}]}
  assert source.extractStreamUrl(metadata) == "https://example.invalid/other.mp4"


def test_extractStreamUrlRaisesWhenMissing():
  """再生できるURLが無い場合にエラーになることを確認する."""
  with pytest.raises(SourceError) as errorInfo:
    source.extractStreamUrl({"title": "no url"})
  assert "--cache" in (errorInfo.value.hint or "")


def test_resolveUrlReturnsStream(monkeypatch):
  """URLがストリーミング再生用の情報へ解決されることを確認する."""
  monkeypatch.setattr(source, "fetchMetadata", lambda url, quality, cookies=None: SAMPLE_METADATA)

  messages: list[str] = []
  playable = source.resolveUrl(SAMPLE_URL, "480", False, messages.append)

  assert playable.path == SAMPLE_METADATA["url"]
  assert playable.title == "テスト動画"
  assert playable.duration == 212
  assert playable.isRemote is True
  assert messages  # 進捗メッセージが通知されている


def test_resolveUrlWithCacheDownloads(monkeypatch, isolatedHome):
  """--cache 指定時にダウンロードした結果を再生対象にすることを確認する."""
  monkeypatch.setattr(source, "fetchMetadata", lambda url, quality, cookies=None: SAMPLE_METADATA)

  expectedPath = source.cachePathFor(SAMPLE_METADATA, SAMPLE_URL, "480")

  def fakeDownload(url, quality, targetPath, notify=None, cookies=None):
    targetPath.parent.mkdir(parents=True, exist_ok=True)
    targetPath.write_bytes(b"\x00")
    return targetPath

  monkeypatch.setattr(source, "downloadToCache", fakeDownload)

  playable = source.resolveUrl(SAMPLE_URL, "480", True)
  assert playable.path == str(expectedPath)
  assert playable.isRemote is False


def test_cookieOptionsBuildsBrowserArgument():
  """ブラウザ指定が yt-dlp の引数へ変換されることを確認する."""
  options = source.AccessOptions(fromBrowser="chrome")
  assert options.toArguments() == ["--cookies-from-browser", "chrome"]


def test_cookieOptionsBuildsFileArgument(tmp_path):
  """Cookieファイルの指定が引数へ変換されることを確認する."""
  cookieFile = tmp_path / "cookies.txt"
  cookieFile.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

  options = source.AccessOptions(filePath=str(cookieFile))
  assert options.toArguments() == ["--cookies", str(cookieFile)]


def test_cookieOptionsRejectsMissingFile(tmp_path):
  """存在しないCookieファイルを指定した場合のエラーを確認する."""
  options = source.AccessOptions(filePath=str(tmp_path / "none.txt"))
  with pytest.raises(SourceError) as errorInfo:
    options.toArguments()
  assert "Cookieファイル" in errorInfo.value.message


def test_cookieOptionsWithoutSettings():
  """Cookieを指定しない場合は引数が増えないことを確認する."""
  assert source.AccessOptions().toArguments() == []


def test_jsRuntimeArgumentsEnablesInstalledRuntimes(monkeypatch):
  """導入済みのJavaScriptランタイムだけを有効化することを確認する."""
  monkeypatch.setattr(
    source.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None
  )
  assert source.jsRuntimeArguments() == ["--js-runtimes", "node"]


def test_jsRuntimeArgumentsPrefersAllAvailable(monkeypatch):
  """複数導入されていれば，優先順に沿ってすべて有効化することを確認する."""
  monkeypatch.setattr(
    source.shutil, "which", lambda name: f"/usr/bin/{name}" if name in ("deno", "node") else None
  )
  assert source.jsRuntimeArguments() == [
    "--js-runtimes",
    "deno",
    "--js-runtimes",
    "node",
  ]


def test_jsRuntimeArgumentsWithoutRuntimes(monkeypatch):
  """ランタイムが無ければ引数を増やさないことを確認する."""
  monkeypatch.setattr(source.shutil, "which", lambda name: None)
  assert source.jsRuntimeArguments() == []


def test_fetchMetadataEnablesJsRuntime(monkeypatch):
  """取得時にJavaScriptランタイムの指定が渡ることを確認する."""
  capturedArguments: list[str] = []

  def fakeRun(arguments, timeout):
    capturedArguments.extend(arguments)
    return makeCompletedProcess(stdout=json.dumps(SAMPLE_METADATA))

  monkeypatch.setattr(source, "runYtdlp", fakeRun)
  monkeypatch.setattr(
    source.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None
  )
  source.fetchMetadata(SAMPLE_URL, "480")

  assert "--js-runtimes" in capturedArguments


def test_accessOptionsBuildsPlayerClientArgument():
  """取得方法の指定が extractor-args へ変換されることを確認する."""
  options = source.AccessOptions(playerClient="mweb")
  assert options.toArguments() == ["--extractor-args", "youtube:player_client=mweb"]


def test_accessOptionsCombinesCookiesAndPlayerClient(tmp_path):
  """Cookieと取得方法を同時に指定できることを確認する."""
  options = source.AccessOptions(fromBrowser="chrome", playerClient="tv")
  arguments = options.toArguments()
  assert arguments[:2] == ["--cookies-from-browser", "chrome"]
  assert arguments[2:] == ["--extractor-args", "youtube:player_client=tv"]


def test_cookieOptionsResolveUsesEnvironment(monkeypatch):
  """環境変数からCookie設定を補えることを確認する."""
  monkeypatch.setenv(config.COOKIES_BROWSER_ENV_VAR, "firefox")
  assert source.AccessOptions.resolve().fromBrowser == "firefox"
  # 明示的な指定は環境変数より優先される
  assert source.AccessOptions.resolve("safari").fromBrowser == "safari"


def test_fetchMetadataPassesCookieArguments(monkeypatch):
  """Cookie設定が yt-dlp の呼び出しへ渡ることを確認する."""
  capturedArguments: list[str] = []

  def fakeRun(arguments, timeout):
    capturedArguments.extend(arguments)
    return makeCompletedProcess(stdout=json.dumps(SAMPLE_METADATA))

  monkeypatch.setattr(source, "runYtdlp", fakeRun)
  source.fetchMetadata(SAMPLE_URL, "480", source.AccessOptions(fromBrowser="chrome"))

  assert "--cookies-from-browser" in capturedArguments
  assert "chrome" in capturedArguments


@pytest.mark.parametrize(
  "errorOutput, expectedKeyword",
  [
    ("ERROR: Sign in to confirm your age.", "年齢制限"),
    ("ERROR: This video may be inappropriate for some users.", "年齢制限"),
    ("ERROR: Sign in to confirm you're not a bot", "確認"),
    ("ERROR: Private video. Sign in if you've been granted access", "非公開"),
    ("ERROR: Join this channel to get access to members-only content", "メンバー限定"),
    ("ERROR: Video unavailable", "削除"),
    (
      "ERROR: This video is age-restricted and only available on YouTube.",
      "--player-client",
    ),
    ("WARNING: Signature solving failed: Some formats may be missing.", "deno"),
    ("WARNING: Only images are available for download.", "yt-dlp-ejs"),
    ("ERROR: something completely different", "yt-dlp -U"),
  ],
)
def test_errorHintForKnownFailures(errorOutput, expectedKeyword):
  """yt-dlp のエラー内容に応じた対処方法が選ばれることを確認する."""
  assert expectedKeyword in source.errorHintFor(errorOutput)


def test_ageRestrictedErrorSuggestsCookies(monkeypatch):
  """年齢制限のエラーでCookieの指定方法が案内されることを確認する."""
  monkeypatch.setattr(source, "ytdlpCommand", lambda: ["yt-dlp"])
  monkeypatch.setattr(
    source.subprocess,
    "run",
    lambda *args, **kwargs: makeCompletedProcess(
      stderr="ERROR: [youtube] abc: Sign in to confirm your age.", returncode=1
    ),
  )

  with pytest.raises(SourceError) as errorInfo:
    source.runYtdlp(["-J", SAMPLE_URL], 10)
  assert "--cookies-from-browser" in (errorInfo.value.hint or "")


def test_cachePathForSanitizesId(isolatedHome):
  """キャッシュのファイル名が安全な文字だけになることを確認する."""
  cachePath = source.cachePathFor({"id": "../evil id", "ext": "mp4"}, SAMPLE_URL, "480")
  assert cachePath.parent == isolatedHome / config.CACHE_DIR_NAME
  assert "/" not in cachePath.name
  assert ".." not in cachePath.name
  assert cachePath.name.endswith(".mp4")


@pytest.mark.parametrize(
  "extension",
  ["../../../outside/file", "/etc/passwd", "mp4/../..", "", "mp4;rm -rf"],
)
def test_cachePathStaysInsideCacheDirectory(isolatedHome, extension):
  """拡張子に細工があってもキャッシュ外へ書き出さないことを確認する."""
  cachePath = source.cachePathFor({"id": "abc", "ext": extension}, SAMPLE_URL, "480")
  cacheDirectory = (isolatedHome / config.CACHE_DIR_NAME).resolve()

  assert cachePath.resolve().parent == cacheDirectory
  assert cachePath.parent == isolatedHome / config.CACHE_DIR_NAME


def test_cacheKeyDiffersByQuality(isolatedHome):
  """画質が違えば別のキャッシュになることを確認する."""
  lowQuality = source.cachePathFor(SAMPLE_METADATA, SAMPLE_URL, "360")
  highQuality = source.cachePathFor(SAMPLE_METADATA, SAMPLE_URL, "720")
  assert lowQuality != highQuality


def test_cacheKeyDiffersByUrl(isolatedHome):
  """動画IDが同じでもURLが違えば別のキャッシュになることを確認する."""
  first = source.cachePathFor(SAMPLE_METADATA, "https://example.com/a", "480")
  second = source.cachePathFor(SAMPLE_METADATA, "https://example.com/b", "480")
  assert first != second


def test_cacheKeyIsStableForSameInput(isolatedHome):
  """同じ入力なら同じキャッシュ名になることを確認する."""
  first = source.cachePathFor(SAMPLE_METADATA, SAMPLE_URL, "480")
  second = source.cachePathFor(SAMPLE_METADATA, SAMPLE_URL, "480")
  assert first == second


def test_partialFileIsNotReusedAsCache(isolatedHome, monkeypatch):
  """途中で終わった小さなファイルを再利用しないことを確認する."""
  cachePath = isolatedHome / config.CACHE_DIR_NAME / "broken.mp4"
  cachePath.parent.mkdir(parents=True, exist_ok=True)
  cachePath.write_bytes(b"\x00" * 10)  # 明らかに不完全なサイズ

  calls: list[list[str]] = []

  def fakeRun(arguments, timeout):
    calls.append(arguments)
    # ダウンロード先（.part）へ十分な大きさのファイルを作る
    partialPath = cachePath.with_name(cachePath.name + source.PARTIAL_SUFFIX)
    partialPath.write_bytes(b"\x00" * (source.MIN_CACHE_FILE_SIZE + 1))
    return makeCompletedProcess()

  monkeypatch.setattr(source, "runYtdlp", fakeRun)
  result = source.downloadToCache(SAMPLE_URL, "480", cachePath)

  assert calls, "壊れたキャッシュがあるのに再取得していません"
  assert result.stat().st_size > source.MIN_CACHE_FILE_SIZE
  assert not result.with_name(result.name + source.PARTIAL_SUFFIX).exists()


def test_incompleteDownloadRaisesAndCleansUp(isolatedHome, monkeypatch):
  """ダウンロードが不完全なら，残骸を消してエラーにすることを確認する."""
  cachePath = isolatedHome / config.CACHE_DIR_NAME / "tiny.mp4"
  cachePath.parent.mkdir(parents=True, exist_ok=True)

  def fakeRun(arguments, timeout):
    partialPath = cachePath.with_name(cachePath.name + source.PARTIAL_SUFFIX)
    partialPath.write_bytes(b"\x00")  # 小さすぎるファイル
    return makeCompletedProcess()

  monkeypatch.setattr(source, "runYtdlp", fakeRun)

  with pytest.raises(SourceError) as errorInfo:
    source.downloadToCache(SAMPLE_URL, "480", cachePath)

  assert "不完全" in errorInfo.value.message
  assert not cachePath.exists()
  assert not cachePath.with_name(cachePath.name + source.PARTIAL_SUFFIX).exists()


def test_downloadToCacheReusesExistingFile(monkeypatch, isolatedHome, capsys):
  """すでにダウンロード済みならyt-dlpを実行しないことを確認する."""
  cachePath = isolatedHome / config.CACHE_DIR_NAME / "video.mp4"
  cachePath.parent.mkdir(parents=True, exist_ok=True)
  cachePath.write_bytes(b"\x00" * (source.MIN_CACHE_FILE_SIZE + 1))

  def failIfCalled(*args, **kwargs):
    raise AssertionError("yt-dlp が実行されました")

  monkeypatch.setattr(source, "runYtdlp", failIfCalled)

  messages: list[str] = []
  assert source.downloadToCache(SAMPLE_URL, "480", cachePath, messages.append) == cachePath
  assert any("キャッシュ" in message for message in messages)


def test_downloadToCacheRaisesWhenFileMissing(monkeypatch, isolatedHome):
  """ダウンロード後にファイルが無い場合はエラーになることを確認する."""
  monkeypatch.setattr(source, "runYtdlp", lambda arguments, timeout: makeCompletedProcess())
  cachePath = isolatedHome / config.CACHE_DIR_NAME / "missing.mp4"

  with pytest.raises(SourceError):
    source.downloadToCache(SAMPLE_URL, None, cachePath)


def test_openSourceWithLocalFile(dummyVideo):
  """ローカルの動画ファイルもそのまま扱えることを確認する."""
  playable = source.openSource(str(dummyVideo))
  assert playable.path == str(dummyVideo)
  assert playable.title == dummyVideo.name
  assert playable.isRemote is False


def test_openSourceWithMissingLocalFile(tmp_path):
  """存在しないファイルを指定した場合のエラーを確認する."""
  with pytest.raises(VideoFileError):
    source.openSource(str(tmp_path / "none.mp4"))


def test_cacheListingAndClear(isolatedHome):
  """キャッシュの一覧取得と削除ができることを確認する."""
  cacheDirectory = isolatedHome / config.CACHE_DIR_NAME
  cacheDirectory.mkdir(parents=True, exist_ok=True)
  (cacheDirectory / "a.mp4").write_bytes(b"\x00" * 10)
  (cacheDirectory / "b.mp4").write_bytes(b"\x00" * 20)

  assert len(source.cachedFiles()) == 2

  removedCount, removedSize = source.clearCache()
  assert removedCount == 2
  assert removedSize == 30
  assert source.cachedFiles() == []


def test_cachedFilesWithoutDirectory():
  """キャッシュディレクトリが無い場合は空の一覧になることを確認する."""
  assert source.cachedFiles() == []
