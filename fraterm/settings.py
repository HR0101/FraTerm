"""毎回指定せずに済むよう，オプションの既定値を保存するモジュール."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from . import config
from .errors import RegistryError

# 既定値として保存できる項目と，値の検証方法
# （キー: 項目名，値: 許容する型または選択肢）
ALLOWED_KEYS: dict[str, Any] = {
  "mode": config.AVAILABLE_MODES,
  "audio": bool,
  "width": (int, type(None)),
  "fps": (float, int, type(None)),
  "preRender": bool,
  "charset": (str, type(None)),
  "brightness": (float, int),
  "contrast": (float, int),
  "color": config.COLOR_CHOICES,
  "volume": (int,),
  "audioOffset": (float, int),
  "quality": config.QUALITY_CHOICES,
  "cache": bool,
  "cookiesFromBrowser": (str, type(None)),
  "cookiesFile": (str, type(None)),
  "playerClient": (str, type(None)),
}


def settingsPath() -> Path:
  """既定値を保存するJSONファイルのパスを返す."""
  return config.configDir() / config.SETTINGS_FILE_NAME


def _isAllowed(key: str, value: Any) -> bool:
  """保存されている値が，その項目として妥当かどうかを判定する."""
  rule = ALLOWED_KEYS.get(key)
  if rule is None:
    return False
  if isinstance(rule, tuple) and rule and isinstance(rule[0], type):
    return isinstance(value, rule)
  if isinstance(rule, tuple):
    return value in rule
  return isinstance(value, rule)


def load() -> dict[str, Any]:
  """保存された既定値を読み込む．壊れている項目は無視する."""
  path = settingsPath()
  if not path.exists():
    return {}

  try:
    rawText = path.read_text(encoding="utf-8")
  except OSError as error:
    raise RegistryError(
      f"既定値の設定を読み込めません: {path}（{error}）",
      hint="ファイルの権限を確認してください．",
    ) from error

  if not rawText.strip():
    return {}

  try:
    data = json.loads(rawText)
  except json.JSONDecodeError as error:
    raise RegistryError(
      f"既定値の設定が壊れています: {path}（{error.lineno}行目付近）",
      hint=f"`{config.commandName()} defaults --clear` で初期化できます．",
    ) from error

  if not isinstance(data, dict):
    return {}

  # 想定外の項目や型が入っていても，そこだけ捨てて残りは活かす
  return {key: value for key, value in data.items() if _isAllowed(key, value)}


def save(values: dict[str, Any]) -> None:
  """既定値を書き出す．一時ファイル経由で安全に置き換える."""
  path = settingsPath()

  try:
    path.parent.mkdir(parents=True, exist_ok=True)
  except OSError as error:
    raise RegistryError(
      f"設定ディレクトリを作成できません: {path.parent}（{error}）"
    ) from error

  payload = {key: value for key, value in sorted(values.items()) if _isAllowed(key, value)}

  temporaryPath: str | None = None
  try:
    with tempfile.NamedTemporaryFile(
      mode="w",
      encoding="utf-8",
      dir=str(path.parent),
      prefix=f".{path.name}.",
      suffix=".tmp",
      delete=False,
    ) as temporaryFile:
      temporaryPath = temporaryFile.name
      json.dump(payload, temporaryFile, ensure_ascii=False, indent=2)
      temporaryFile.write("\n")
      temporaryFile.flush()
      os.fsync(temporaryFile.fileno())
    os.replace(temporaryPath, path)
    temporaryPath = None
  except OSError as error:
    raise RegistryError(
      f"既定値の設定を書き込めません: {path}（{error}）",
      hint="ディスクの空き容量とファイルの権限を確認してください．",
    ) from error
  finally:
    if temporaryPath is not None and os.path.exists(temporaryPath):
      os.unlink(temporaryPath)


def update(changes: dict[str, Any]) -> dict[str, Any]:
  """既定値を部分的に変更し，変更後の内容を返す."""
  values = load()
  values.update(changes)
  save(values)
  return values


def clear() -> None:
  """保存された既定値をすべて削除する."""
  path = settingsPath()
  try:
    path.unlink(missing_ok=True)
  except OSError as error:
    raise RegistryError(f"既定値の設定を削除できません: {path}（{error}）") from error
