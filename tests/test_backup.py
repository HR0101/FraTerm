"""設定と登録動画のバックアップ・復元テスト."""

from __future__ import annotations

import json

import pytest

from fraterm import backup, cli, settings
from fraterm.errors import RegistryError
from fraterm.registry import Registry, VideoEntry


def test_backupRoundTrip(tmp_path, dummyVideo):
  """登録動画と既定値を同じ内容で復元できることを確認する."""
  entry = VideoEntry(name="sample", path=str(dummyVideo), preRender=True)
  target = tmp_path / "fraterm-backup.json"

  backup.write(target, {entry.name: entry}, {"fps": 60, "preRender": True})
  entries, defaults = backup.read(target)

  assert entries["sample"].path == str(dummyVideo)
  assert entries["sample"].preRender is True
  assert defaults == {"fps": 60, "preRender": True}


def test_backupRejectsUnknownVersion(tmp_path):
  """未対応のバックアップ形式を拒否することを確認する."""
  target = tmp_path / "old.json"
  target.write_text(
    json.dumps({"format": "fraterm-backup", "version": 999}), encoding="utf-8"
  )

  with pytest.raises(RegistryError):
    backup.read(target)


def test_exportAndImportCommands(tmp_path, dummyVideo, capsys):
  """export/importコマンドで設定を別状態へ移行できることを確認する."""
  cli.main(["add", "sample", str(dummyVideo), "--pre-render"])
  cli.main(["defaults", "--fps", "60"])
  capsys.readouterr()
  target = tmp_path / "backup.json"

  assert cli.main(["export", str(target)]) == cli.EXIT_OK
  Registry().remove("sample")
  settings.clear()

  assert cli.main(["import", str(target)]) == cli.EXIT_OK
  assert Registry().get("sample").preRender is True
  assert settings.load()["fps"] == 60
