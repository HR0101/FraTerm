"""登録動画と既定値のバックアップを扱うモジュール."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from . import settings
from .errors import RegistryError
from .registry import VideoEntry, validateName

BACKUP_FORMAT = "fraterm-backup"
BACKUP_VERSION = 1


def createData(entries: dict[str, VideoEntry], defaults: dict[str, Any]) -> dict[str, Any]:
  """現在の登録情報と既定値をバックアップ形式へまとめる."""
  return {
    "format": BACKUP_FORMAT,
    "version": BACKUP_VERSION,
    "settings": settings.filterAllowed(defaults),
    "videos": {name: entry.toDict() for name, entry in sorted(entries.items())},
  }


def write(path: Path | str, entries: dict[str, VideoEntry], defaults: dict[str, Any]) -> Path:
  """バックアップを指定先へ安全に書き出す."""
  target = Path(path).expanduser()
  try:
    target.parent.mkdir(parents=True, exist_ok=True)
  except OSError as error:
    raise RegistryError(f"バックアップ先を作成できません: {target.parent}（{error}）") from error

  temporaryPath: str | None = None
  try:
    with tempfile.NamedTemporaryFile(
      mode="w",
      encoding="utf-8",
      dir=str(target.parent),
      prefix=f".{target.name}.",
      suffix=".tmp",
      delete=False,
    ) as temporaryFile:
      temporaryPath = temporaryFile.name
      json.dump(createData(entries, defaults), temporaryFile, ensure_ascii=False, indent=2)
      temporaryFile.write("\n")
      temporaryFile.flush()
      os.fsync(temporaryFile.fileno())
    os.replace(temporaryPath, target)
    temporaryPath = None
  except OSError as error:
    raise RegistryError(f"バックアップを書き出せません: {target}（{error}）") from error
  finally:
    if temporaryPath is not None and os.path.exists(temporaryPath):
      os.unlink(temporaryPath)
  return target


def read(path: Path | str) -> tuple[dict[str, VideoEntry], dict[str, Any]]:
  """バックアップを検証して，登録情報と既定値を返す."""
  source = Path(path).expanduser()
  try:
    rawText = source.read_text(encoding="utf-8")
  except OSError as error:
    raise RegistryError(f"バックアップを読み込めません: {source}（{error}）") from error

  try:
    data = json.loads(rawText)
  except json.JSONDecodeError as error:
    raise RegistryError(
      f"バックアップの形式が壊れています: {source}（{error.lineno}行目付近）"
    ) from error

  if not isinstance(data, dict):
    raise RegistryError("バックアップのルートがオブジェクトではありません．")
  if data.get("format") != BACKUP_FORMAT or data.get("version") != BACKUP_VERSION:
    raise RegistryError(
      "対応していないFraTermバックアップです．",
      hint=f"対応形式: {BACKUP_FORMAT} v{BACKUP_VERSION}",
    )

  rawSettings = data.get("settings", {})
  if not isinstance(rawSettings, dict):
    raise RegistryError("バックアップの既定値が正しくありません．")
  defaults = settings.filterAllowed(rawSettings)

  rawVideos = data.get("videos", {})
  if not isinstance(rawVideos, dict):
    raise RegistryError("バックアップの登録動画が正しくありません．")
  entries: dict[str, VideoEntry] = {}
  for name, rawEntry in rawVideos.items():
    if not isinstance(name, str):
      raise RegistryError("バックアップに不正な登録名があります．")
    validateName(name)
    if not isinstance(rawEntry, dict):
      raise RegistryError(f"「{name}」の登録内容が壊れています．")
    entries[name] = VideoEntry.fromDict(name, rawEntry)

  return entries, defaults
