"""登録情報の保存と取得に関するテスト."""

from __future__ import annotations

import json
import os

import pytest

from fraterm import config
from fraterm.errors import (
  InvalidNameError,
  NameAlreadyExistsError,
  NameNotFoundError,
  RegistryError,
  VideoFileError,
)
from fraterm.registry import Registry, VideoEntry, resolveVideoPath, validateName


def makeEntry(name: str, path, **overrides) -> VideoEntry:
  """テスト用の登録情報を作る."""
  values = {"name": name, "path": str(path)}
  values.update(overrides)
  return VideoEntry(**values)


def test_addAndGetEntry(dummyVideo):
  """登録した内容をそのまま取得できることを確認する."""
  registry = Registry()
  registry.add(makeEntry("sample", dummyVideo, mode="color", audio=True, width=100))

  entry = registry.get("sample")
  assert entry.path == str(dummyVideo)
  assert entry.mode == "color"
  assert entry.audio is True
  assert entry.width == 100


def test_registryFileIsCreatedAtConfiguredPath(dummyVideo, isolatedHome):
  """設定ファイルが所定の場所へ作られることを確認する."""
  Registry().add(makeEntry("sample", dummyVideo))

  registryFile = isolatedHome / config.REGISTRY_FILE_NAME
  assert registryFile.is_file()

  savedData = json.loads(registryFile.read_text(encoding="utf-8"))
  assert savedData["sample"]["path"] == str(dummyVideo)


def test_relativePathIsStoredAsAbsolute(tmp_path, monkeypatch):
  """相対パスが絶対パスとして保存されることを確認する."""
  videoFile = tmp_path / "movie.mp4"
  videoFile.write_bytes(b"\x00")
  monkeypatch.chdir(tmp_path)

  resolvedPath = resolveVideoPath("movie.mp4")
  assert os.path.isabs(resolvedPath)
  assert resolvedPath.endswith("movie.mp4")


def test_missingVideoCannotBeRegistered(tmp_path):
  """存在しない動画は登録できないことを確認する."""
  with pytest.raises(VideoFileError):
    resolveVideoPath(str(tmp_path / "notfound.mp4"))


def test_directoryIsRejected(tmp_path):
  """ディレクトリを動画として登録できないことを確認する."""
  with pytest.raises(VideoFileError):
    resolveVideoPath(str(tmp_path))


def test_duplicateNameRequiresForce(dummyVideo):
  """同名の登録は --force なしでは上書きできないことを確認する."""
  registry = Registry()
  registry.add(makeEntry("sample", dummyVideo, mode="ascii"))

  with pytest.raises(NameAlreadyExistsError):
    registry.add(makeEntry("sample", dummyVideo, mode="color"))

  registry.add(makeEntry("sample", dummyVideo, mode="color"), force=True)
  assert registry.get("sample").mode == "color"


@pytest.mark.parametrize("invalidName", ["my movie", "", "-name", "名前", "a" * 100])
def test_invalidNamesAreRejected(invalidName):
  """使用できない登録名が拒否されることを確認する."""
  with pytest.raises(InvalidNameError):
    validateName(invalidName)


@pytest.mark.parametrize("reservedName", ["list", "play", "add", "remove", "run"])
def test_reservedNamesAreRejected(reservedName):
  """コマンド名と重複する登録名が拒否されることを確認する."""
  with pytest.raises(InvalidNameError):
    validateName(reservedName)


@pytest.mark.parametrize("validName", ["badapple", "neko_2", "bad-apple", "v1.0"])
def test_validNamesAreAccepted(validName):
  """使用できる登録名が受け入れられることを確認する."""
  validateName(validName)


def test_removeDeletesOnlyRegistration(dummyVideo):
  """削除しても動画ファイル自体は残ることを確認する."""
  registry = Registry()
  registry.add(makeEntry("sample", dummyVideo))

  registry.remove("sample")
  assert registry.names() == []
  assert dummyVideo.exists()


def test_removeUnknownNameRaises():
  """未登録の名前を削除しようとするとエラーになることを確認する."""
  with pytest.raises(NameNotFoundError):
    Registry().remove("unknown")


def test_getUnknownNameRaises():
  """未登録の名前を取得しようとするとエラーになることを確認する."""
  with pytest.raises(NameNotFoundError):
    Registry().get("unknown")


def test_updateChangesOnlySpecifiedFields(dummyVideo):
  """update が指定した項目だけを変更することを確認する."""
  registry = Registry()
  registry.add(makeEntry("sample", dummyVideo, mode="ascii", audio=False, width=80))

  updatedEntry = registry.update("sample", {"mode": "color", "audio": True})
  assert updatedEntry.mode == "color"
  assert updatedEntry.audio is True
  assert updatedEntry.width == 80


def test_japanesePathIsPreserved(tmp_path):
  """日本語を含むパスを保存・読み込みできることを確認する."""
  videoFile = tmp_path / "動画テスト.mp4"
  videoFile.write_bytes(b"\x00")

  registry = Registry()
  registry.add(makeEntry("japanese", videoFile))
  assert registry.get("japanese").path == str(videoFile)


def test_brokenJsonRaisesRegistryError(isolatedHome):
  """壊れたJSONに対して分かりやすいエラーになることを確認する."""
  isolatedHome.mkdir(parents=True, exist_ok=True)
  (isolatedHome / config.REGISTRY_FILE_NAME).write_text("{ broken", encoding="utf-8")

  with pytest.raises(RegistryError):
    Registry().load()


def test_emptyFileIsTreatedAsNoEntries(isolatedHome):
  """空の設定ファイルは登録なしとして扱われることを確認する."""
  isolatedHome.mkdir(parents=True, exist_ok=True)
  (isolatedHome / config.REGISTRY_FILE_NAME).write_text("", encoding="utf-8")

  assert Registry().load() == {}


def test_missingFileReturnsEmptyRegistry():
  """設定ファイルが無い場合は空の辞書を返すことを確認する."""
  assert Registry().load() == {}


def test_saveFailureKeepsPreviousContent(dummyVideo, isolatedHome, monkeypatch):
  """保存に失敗しても直前の設定が壊れないことを確認する."""
  registry = Registry()
  registry.add(makeEntry("sample", dummyVideo, mode="ascii"))
  originalText = (isolatedHome / config.REGISTRY_FILE_NAME).read_text(encoding="utf-8")

  def failingReplace(*args, **kwargs):
    raise OSError("書き込みに失敗しました")

  monkeypatch.setattr(os, "replace", failingReplace)
  with pytest.raises(RegistryError):
    registry.add(makeEntry("another", dummyVideo), force=True)

  assert (isolatedHome / config.REGISTRY_FILE_NAME).read_text(encoding="utf-8") == originalText
  assert registry.names() == ["sample"]


def test_unknownModeFallsBackToDefault(dummyVideo, isolatedHome):
  """未知の描画モードが既定値へ置き換わることを確認する."""
  isolatedHome.mkdir(parents=True, exist_ok=True)
  (isolatedHome / config.REGISTRY_FILE_NAME).write_text(
    json.dumps({"sample": {"path": str(dummyVideo), "mode": "hologram"}}),
    encoding="utf-8",
  )

  assert Registry().get("sample").mode == config.DEFAULT_MODE


def test_entryWithoutPathRaises(isolatedHome, dummyVideo):
  """パスが欠けた登録内容がエラーになることを確認する."""
  isolatedHome.mkdir(parents=True, exist_ok=True)
  (isolatedHome / config.REGISTRY_FILE_NAME).write_text(
    json.dumps({"sample": {"mode": "ascii"}}), encoding="utf-8"
  )

  with pytest.raises(RegistryError):
    Registry().load()


def test_resolvedCharsetUsesPreset(dummyVideo):
  """プリセット名が実際の文字セットへ解決されることを確認する."""
  entry = makeEntry("sample", dummyVideo, charset="simple")
  assert entry.resolvedCharset() == config.CHARSET_PRESETS["simple"]
