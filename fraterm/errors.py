"""FraTerm 全体で使用する例外を定義するモジュール."""

from __future__ import annotations


class FraTermError(Exception):
  """利用者へそのまま提示できるエラーの基底クラス."""

  def __init__(self, message: str, hint: str | None = None) -> None:
    super().__init__(message)
    self.message = message
    # hint には「次に何をすればよいか」を日本語で入れる
    self.hint = hint

  def __str__(self) -> str:
    return self.message


class RegistryError(FraTermError):
  """登録データの読み書きに失敗した場合のエラー."""


class NameNotFoundError(FraTermError):
  """指定された登録名が存在しない場合のエラー."""


class NameAlreadyExistsError(FraTermError):
  """同じ登録名がすでに存在する場合のエラー."""


class InvalidNameError(FraTermError):
  """登録名として使用できない文字列が指定された場合のエラー."""


class VideoFileError(FraTermError):
  """動画ファイルが存在しない，または読み込めない場合のエラー."""


class PlaybackError(FraTermError):
  """再生処理そのものに失敗した場合のエラー."""


class AudioError(FraTermError):
  """音声再生に必要な外部コマンドが利用できない場合のエラー."""
