"""動画の登録情報を保存・取得するモジュール."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from . import config
from .errors import (
  InvalidNameError,
  NameAlreadyExistsError,
  NameNotFoundError,
  RegistryError,
  VideoFileError,
)

# 登録名として許可する文字．先頭は英数字またはアンダースコアとする
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")

# サブコマンドと衝突する名前は登録できないようにする（定義は config が一元管理する）
RESERVED_NAMES = config.RESERVED_NAMES

# 登録名の最大長
MAX_NAME_LENGTH = 64


@dataclass(frozen=True)
class VideoEntry:
  """1件の動画登録情報を表すデータクラス."""

  name: str
  path: str
  mode: str = config.DEFAULT_MODE
  audio: bool = False
  width: int | None = None
  fps: float | None = None
  charset: str | None = None
  brightness: float = config.DEFAULT_BRIGHTNESS
  contrast: float = config.DEFAULT_CONTRAST
  color: str = config.DEFAULT_COLOR
  volume: int = config.DEFAULT_VOLUME
  audioOffset: float = config.DEFAULT_AUDIO_OFFSET
  audioEffect: str = config.DEFAULT_AUDIO_EFFECT
  # 以下はURLを登録した場合にのみ使用する
  quality: str | None = None
  cache: bool = False
  # ログインが必要な動画向けのCookie設定
  cookiesFromBrowser: str | None = None
  cookiesFile: str | None = None
  # YouTubeの取得方法（プレイヤークライアント）の指定
  playerClient: str | None = None
  # ダウンロード済みファイルの場所と，その取得に使った画質
  cachedPath: str | None = None
  cachedQuality: str | None = None

  def toDict(self) -> dict[str, Any]:
    """JSONへ保存する形式の辞書を返す（登録名はキーになるため含めない）."""
    return {
      "path": self.path,
      "mode": self.mode,
      "audio": self.audio,
      "width": self.width,
      "fps": self.fps,
      "charset": self.charset,
      "brightness": self.brightness,
      "contrast": self.contrast,
      "color": self.color,
      "volume": self.volume,
      "audioOffset": self.audioOffset,
      "audioEffect": self.audioEffect,
      "quality": self.quality,
      "cache": self.cache,
      "cookiesFromBrowser": self.cookiesFromBrowser,
      "cookiesFile": self.cookiesFile,
      "playerClient": self.playerClient,
      "cachedPath": self.cachedPath,
      "cachedQuality": self.cachedQuality,
    }

  @classmethod
  def fromDict(cls, name: str, data: dict[str, Any]) -> "VideoEntry":
    """JSONから読み込んだ辞書を VideoEntry へ変換する."""
    if not isinstance(data, dict):
      raise RegistryError(
        f"「{name}」の登録内容が壊れています．",
        hint=f"設定ファイル {config.registryPath()} を確認してください．",
      )

    path = data.get("path")
    if not isinstance(path, str) or not path:
      raise RegistryError(
        f"「{name}」の登録内容に動画ファイルのパスがありません．",
        hint=f"設定ファイル {config.registryPath()} を確認してください．",
      )

    mode = data.get("mode") or config.DEFAULT_MODE
    if mode not in config.AVAILABLE_MODES:
      mode = config.DEFAULT_MODE

    return cls(
      name=name,
      path=path,
      mode=mode,
      audio=bool(data.get("audio", False)),
      width=_optionalInt(data.get("width")),
      fps=_optionalFloat(data.get("fps")),
      charset=data.get("charset") if isinstance(data.get("charset"), str) else None,
      brightness=_floatOrDefault(data.get("brightness"), config.DEFAULT_BRIGHTNESS),
      contrast=_floatOrDefault(data.get("contrast"), config.DEFAULT_CONTRAST),
      color=(
        data.get("color")
        if data.get("color") in config.COLOR_CHOICES
        else config.DEFAULT_COLOR
      ),
      volume=_intInRange(
        data.get("volume"), config.DEFAULT_VOLUME, config.MIN_VOLUME, config.MAX_VOLUME
      ),
      audioOffset=_floatOrDefault(data.get("audioOffset"), config.DEFAULT_AUDIO_OFFSET),
      audioEffect=(
        data.get("audioEffect")
        if data.get("audioEffect") in config.AUDIO_EFFECT_CHOICES
        else config.DEFAULT_AUDIO_EFFECT
      ),
      quality=data.get("quality") if isinstance(data.get("quality"), str) else None,
      cache=bool(data.get("cache", False)),
      cookiesFromBrowser=_optionalText(data.get("cookiesFromBrowser")),
      cookiesFile=_optionalText(data.get("cookiesFile")),
      playerClient=_optionalText(data.get("playerClient")),
      cachedPath=(
        data.get("cachedPath") if isinstance(data.get("cachedPath"), str) else None
      ),
      cachedQuality=_optionalText(data.get("cachedQuality")),
    )

  def cachedFile(self) -> Path | None:
    """ダウンロード済みファイルが残っていれば，そのパスを返す."""
    if not self.cachedPath:
      return None
    cachedFilePath = Path(self.cachedPath)
    return cachedFilePath if cachedFilePath.is_file() else None

  def resolvedCharset(self) -> str:
    """プリセット名を解決した実際の文字セットを返す."""
    return config.resolveCharset(self.charset)

  @property
  def isRemote(self) -> bool:
    """登録内容がURLかどうかを返す."""
    return config.isUrl(self.path)

  def videoExists(self) -> bool:
    """再生できる状態かどうかを返す．URLは再生時まで確認しない."""
    if self.isRemote:
      return True
    return Path(self.path).is_file()


def _optionalInt(value: Any) -> int | None:
  """None を許容する整数へ変換する．変換できない場合は None を返す."""
  if value is None:
    return None
  try:
    return int(value)
  except (TypeError, ValueError):
    return None


def _optionalFloat(value: Any) -> float | None:
  """None を許容する実数へ変換する．変換できない場合は None を返す."""
  if value is None:
    return None
  try:
    return float(value)
  except (TypeError, ValueError):
    return None


def _optionalText(value: Any) -> str | None:
  """文字列であればそのまま，そうでなければ None を返す."""
  return value if isinstance(value, str) and value else None


def _intInRange(value: Any, default: int, minimum: int, maximum: int) -> int:
  """範囲内の整数へ変換する．変換できない場合は既定値を返す."""
  converted = _optionalInt(value)
  if converted is None:
    return default
  return max(minimum, min(maximum, converted))


def _floatOrDefault(value: Any, default: float) -> float:
  """実数へ変換できない場合は既定値を返す."""
  converted = _optionalFloat(value)
  return default if converted is None else converted


def validateName(name: str) -> None:
  """登録名として使用できるかどうかを検証する．問題があれば例外を送出する."""
  if not name:
    raise InvalidNameError("登録名が空です．")

  if len(name) > MAX_NAME_LENGTH:
    raise InvalidNameError(
      f"登録名が長すぎます（最大{MAX_NAME_LENGTH}文字）．"
    )

  if not NAME_PATTERN.match(name):
    raise InvalidNameError(
      f"「{name}」は登録名として使用できません．",
      hint="英数字，アンダースコア，ハイフン，ピリオドのみ使用できます（空白は使用できません）．",
    )

  if name.lower() in RESERVED_NAMES:
    raise InvalidNameError(
      f"「{name}」はコマンド名と重複するため使用できません．",
      hint="別の登録名を指定してください．",
    )


def resolveVideoPath(rawPath: str) -> str:
  """入力されたパスを検証し，絶対パスの文字列として返す."""
  candidate = Path(rawPath).expanduser()
  try:
    resolved = candidate.resolve()
  except OSError as error:  # 解決できないパスはそのままエラーにする
    raise VideoFileError(f"パスを解決できません: {rawPath}（{error}）") from error

  if not resolved.exists():
    raise VideoFileError(
      f"動画ファイルが見つかりません: {resolved}",
      hint="パスが正しいか確認してください．",
    )
  if not resolved.is_file():
    raise VideoFileError(f"動画ファイルではありません: {resolved}")

  return str(resolved)


class Registry:
  """videos.json への登録情報の読み書きを担当するクラス."""

  def __init__(self, path: Path | str | None = None) -> None:
    # path を省略した場合は，実行時のOS設定に従った既定の場所を使用する
    self.path = Path(path) if path is not None else config.registryPath()

  # -------------------------------------------------------------------------
  # 読み書き
  # -------------------------------------------------------------------------

  def load(self) -> dict[str, VideoEntry]:
    """登録情報をすべて読み込む．ファイルが無い場合は空の辞書を返す."""
    if not self.path.exists():
      return {}

    try:
      rawText = self.path.read_text(encoding="utf-8")
    except OSError as error:
      raise RegistryError(
        f"設定ファイルを読み込めません: {self.path}（{error}）",
        hint="ファイルの権限を確認してください．",
      ) from error

    if not rawText.strip():
      return {}

    try:
      data = json.loads(rawText)
    except json.JSONDecodeError as error:
      raise RegistryError(
        f"設定ファイルの形式が壊れています: {self.path}（{error.lineno}行目付近）",
        hint="内容を修正するか，ファイルを削除して登録し直してください．",
      ) from error

    if not isinstance(data, dict):
      raise RegistryError(
        f"設定ファイルの形式が正しくありません: {self.path}",
        hint="内容を修正するか，ファイルを削除して登録し直してください．",
      )

    entries: dict[str, VideoEntry] = {}
    for name, entryData in data.items():
      entries[name] = VideoEntry.fromDict(name, entryData)
    return entries

  def save(self, entries: dict[str, VideoEntry]) -> None:
    """登録情報をすべて書き出す．一時ファイル経由で安全に置き換える."""
    payload = {name: entry.toDict() for name, entry in sorted(entries.items())}

    try:
      self.path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
      raise RegistryError(
        f"設定ディレクトリを作成できません: {self.path.parent}（{error}）"
      ) from error

    temporaryPath: str | None = None
    try:
      # 同じディレクトリに一時ファイルを作り，最後に置き換えることで
      # 書き込み失敗時も既存の設定を壊さないようにする
      with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(self.path.parent),
        prefix=f".{self.path.name}.",
        suffix=".tmp",
        delete=False,
      ) as temporaryFile:
        temporaryPath = temporaryFile.name
        json.dump(payload, temporaryFile, ensure_ascii=False, indent=2)
        temporaryFile.write("\n")
        temporaryFile.flush()
        os.fsync(temporaryFile.fileno())
      os.replace(temporaryPath, self.path)
      temporaryPath = None
    except OSError as error:
      raise RegistryError(
        f"設定ファイルへ書き込めません: {self.path}（{error}）",
        hint="ディスクの空き容量とファイルの権限を確認してください．",
      ) from error
    finally:
      if temporaryPath is not None and os.path.exists(temporaryPath):
        os.unlink(temporaryPath)

  # -------------------------------------------------------------------------
  # 操作
  # -------------------------------------------------------------------------

  def names(self) -> list[str]:
    """登録名の一覧を並べ替えて返す."""
    return sorted(self.load().keys())

  def get(self, name: str) -> VideoEntry:
    """登録名から登録情報を取得する．存在しない場合は例外を送出する."""
    entries = self.load()
    if name not in entries:
      raise NameNotFoundError(
        f"「{name}」は登録されていません．",
        hint=f"登録一覧は `{config.commandName()} list` で確認できます．",
      )
    return entries[name]

  def add(self, entry: VideoEntry, force: bool = False) -> VideoEntry:
    """新しい登録を追加する．force が偽で同名が存在する場合は例外を送出する."""
    validateName(entry.name)

    entries = self.load()
    if entry.name in entries and not force:
      raise NameAlreadyExistsError(
        f"「{entry.name}」はすでに登録されています．",
        hint="上書きする場合は --force を指定してください．",
      )

    entries[entry.name] = entry
    self.save(entries)
    return entry

  def update(self, name: str, changes: dict[str, Any]) -> VideoEntry:
    """登録済みの設定を部分的に変更する."""
    entries = self.load()
    if name not in entries:
      raise NameNotFoundError(
        f"「{name}」は登録されていません．",
        hint=f"登録一覧は `{config.commandName()} list` で確認できます．",
      )

    updatedEntry = replace(entries[name], **changes)
    entries[name] = updatedEntry
    self.save(entries)
    return updatedEntry

  def remove(self, name: str) -> VideoEntry:
    """登録を削除する．動画ファイル自体は削除しない."""
    entries = self.load()
    if name not in entries:
      raise NameNotFoundError(
        f"「{name}」は登録されていません．",
        hint=f"登録一覧は `{config.commandName()} list` で確認できます．",
      )

    removedEntry = entries.pop(name)
    self.save(entries)
    return removedEntry
