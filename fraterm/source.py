"""URLや動画ファイルを，再生可能な入力へ解決するモジュール."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import config
from .config import isUrl
from .errors import SourceError
from .registry import resolveVideoPath

YTDLP_COMMAND = "yt-dlp"

# キャッシュ名を組み立てる際の上限と既定値
MAX_ID_LENGTH = 48
MAX_EXTENSION_LENGTH = 8
DEFAULT_EXTENSION = "mp4"
URL_DIGEST_LENGTH = 10

# ダウンロード途中のファイルに付ける拡張子
PARTIAL_SUFFIX = ".part"

# これより小さいファイルは失敗した残骸とみなす
MIN_CACHE_FILE_SIZE = 1024

# YouTubeの署名解読に使えるJavaScriptランタイム（yt-dlp の優先順）
# yt-dlp は既定で deno しか有効にしないため，導入済みのものを明示的に有効化する
JS_RUNTIMES = ("deno", "node", "quickjs", "bun")

# yt-dlp の実行を打ち切るまでの秒数
# Cookieの読み出しや署名解読に時間がかかるため，余裕を持たせる
METADATA_TIMEOUT = 180
DOWNLOAD_TIMEOUT = 1800

# エラー表示に使用する yt-dlp の出力行数
ERROR_LINE_LIMIT = 3

# エラー内容として表示する最大文字数
MAX_DETAIL_LENGTH = 200

# これ以降は yt-dlp 自身の英語の案内なので表示しない
DETAIL_CUT_MARKERS = (" Use --cookies", " See http", " Also see", " Sign in if")

# 進捗メッセージを受け取る関数の型
NotifyFunction = Callable[[str], None]


# ログインが必要な場合に共通で案内する対処方法
COOKIE_HINT = (
  "`--cookies-from-browser chrome` のように，ログイン済みブラウザを指定してください"
  "（safari，firefox なども指定できます）．"
)

# yt-dlp のエラー内容ごとに，利用者へ示す対処方法
YTDLP_ERROR_HINTS = (
  (
    "only available on youtube",
    "埋め込み再生が制限された年齢制限動画です．ログイン済みCookieに加えて "
    "`--player-client mweb`（または tv）をお試しください．"
    "アカウント側で年齢確認が済んでいる必要があります．",
  ),
  ("confirm your age", f"年齢制限のある動画です．{COOKIE_HINT}"),
  ("inappropriate for some users", f"年齢制限のある動画です．{COOKIE_HINT}"),
  ("not a bot", f"YouTube側から本人確認を求められています．{COOKIE_HINT}"),
  ("private video", f"非公開の動画です．閲覧権限のあるアカウントが必要です．{COOKIE_HINT}"),
  ("members-only", f"メンバー限定の動画です．{COOKIE_HINT}"),
  ("this channel's members", f"メンバー限定の動画です．{COOKIE_HINT}"),
  ("video unavailable", "動画が削除されたか，地域制限で視聴できない可能性があります．"),
  ("unsupported url", "このURLには対応していません．動画ページのURLを指定してください．"),
  ("unable to download webpage", "接続できません．ネットワーク状態を確認してください．"),
  ("could not copy", "ブラウザのCookieを読み出せません．ブラウザを終了してから再実行してください．"),
  ("unsupported browser", "対応していないブラウザ名です．"),
  (
    "signature solving failed",
    "YouTubeの署名解読にJavaScriptランタイムが必要です．"
    "`brew install deno`（または Node.js 22以上）を導入してください．",
  ),
  (
    "only images are available",
    "映像の形式を取得できませんでした．"
    "`brew install deno`（または Node.js 22以上）と `python -m pip install yt-dlp-ejs` "
    "を導入すると解決することがあります．",
  ),
)

# 上記に当てはまらない場合の一般的な対処方法
DEFAULT_ERROR_HINT = "URLが正しいか，`yt-dlp -U` で更新が必要でないか確認してください．"


@dataclass
class AccessOptions:
  """ログイン情報や取得方法など，yt-dlp へ渡すアクセス設定."""

  fromBrowser: str | None = None
  filePath: str | None = None
  playerClient: str | None = None

  @classmethod
  def resolve(
    cls,
    fromBrowser: str | None = None,
    filePath: str | None = None,
    playerClient: str | None = None,
  ) -> "AccessOptions":
    """Cookieの指定が無い場合は環境変数の設定を使う."""
    browserValue = fromBrowser or os.environ.get(config.COOKIES_BROWSER_ENV_VAR) or None
    fileValue = filePath or os.environ.get(config.COOKIES_FILE_ENV_VAR) or None
    return cls(
      fromBrowser=browserValue, filePath=fileValue, playerClient=playerClient
    )

  def toArguments(self) -> list[str]:
    """yt-dlp のコマンドライン引数へ変換する."""
    arguments: list[str] = []

    if self.fromBrowser:
      arguments.extend(["--cookies-from-browser", self.fromBrowser])

    if self.filePath:
      cookieFile = Path(self.filePath).expanduser()
      if not cookieFile.is_file():
        raise SourceError(
          f"Cookieファイルが見つかりません: {cookieFile}",
          hint="ブラウザの拡張機能などで書き出したファイルのパスを指定してください．",
        )
      arguments.extend(["--cookies", str(cookieFile)])

    if self.playerClient:
      # YouTubeの取得方法（プレイヤークライアント）を切り替える
      arguments.extend(
        ["--extractor-args", f"youtube:player_client={self.playerClient}"]
      )

    return arguments


@dataclass
class PlayableSource:
  """再生対象として確定した入力を表すデータクラス."""

  path: str
  title: str
  duration: float | None = None
  isRemote: bool = False


def isAvailable() -> bool:
  """yt-dlp を利用できるかどうかを返す."""
  if shutil.which(YTDLP_COMMAND) is not None:
    return True
  return importlib.util.find_spec("yt_dlp") is not None


def ytdlpCommand() -> list[str]:
  """yt-dlp を実行するためのコマンドを組み立てる."""
  executablePath = shutil.which(YTDLP_COMMAND)
  if executablePath is not None:
    return [executablePath]

  # コマンドが無くても，同じPython環境に入っていればモジュールとして実行する
  if importlib.util.find_spec("yt_dlp") is not None:
    return [sys.executable, "-m", "yt_dlp"]

  raise SourceError(
    "URLの再生に必要な yt-dlp が見つかりません．",
    hint="`python -m pip install yt-dlp` を実行してください．",
  )


def jsRuntimeArguments() -> list[str]:
  """導入済みのJavaScriptランタイムを yt-dlp へ有効化させる引数を組み立てる.

  YouTubeは署名の解読にJavaScriptの実行を必要とするが，yt-dlp が既定で有効に
  するのは deno だけである．node などが入っていれば併せて有効化する.
  """
  arguments: list[str] = []
  for runtimeName in JS_RUNTIMES:
    if shutil.which(runtimeName) is not None:
      arguments.extend(["--js-runtimes", runtimeName])
  return arguments


def formatSelector(quality: str | None) -> str:
  """画質の指定を yt-dlp のフォーマット指定へ変換する.

  映像と音声が1つにまとまった形式を優先して選ぶ．
  分離した形式を選ぶと結合にFFmpegが必要になり，音声も再生できなくなるため．
  """
  qualityValue = (quality or config.DEFAULT_QUALITY).lower()
  progressive = "[vcodec!=none][acodec!=none]"

  if qualityValue == "best":
    return f"best{progressive}/best"
  if qualityValue == "worst":
    return f"worst{progressive}/worst"

  try:
    height = int(qualityValue.rstrip("p"))
  except ValueError as error:
    raise SourceError(
      f"画質の指定が正しくありません: {quality}",
      hint=f"指定できる値: {'，'.join(config.QUALITY_CHOICES)}",
    ) from error

  return (
    f"best{progressive}[height<={height}]/best{progressive}/best[height<={height}]/best"
  )


def runYtdlp(arguments: list[str], timeoutSeconds: int) -> subprocess.CompletedProcess:
  """yt-dlp を実行し，失敗した場合は分かりやすいエラーへ変換する."""
  command = ytdlpCommand() + arguments

  try:
    completed = subprocess.run(
      command,
      capture_output=True,
      text=True,
      timeout=timeoutSeconds,
      check=False,
    )
  except subprocess.TimeoutExpired as error:
    raise SourceError(
      f"yt-dlp の応答がありません（{timeoutSeconds}秒でタイムアウトしました）．",
      hint="ネットワーク接続を確認してください．",
    ) from error
  except OSError as error:
    raise SourceError(f"yt-dlp を実行できません（{error}）．") from error

  if completed.returncode != 0:
    raise SourceError(
      f"URLの情報を取得できません．{extractErrorDetail(completed.stderr)}",
      hint=errorHintFor(completed.stderr),
    )

  return completed


def extractErrorDetail(errorOutput: str) -> str:
  """yt-dlp のエラー出力から，表示に適した部分を抜き出す."""
  lines = [line.strip() for line in errorOutput.splitlines() if line.strip()]
  if not lines:
    return ""

  detail = " / ".join(lines[-ERROR_LINE_LIMIT:])

  # yt-dlp 自身の英語の案内は，日本語の対処方法と重複するため取り除く
  for marker in DETAIL_CUT_MARKERS:
    markerIndex = detail.find(marker)
    if markerIndex > 0:
      detail = detail[:markerIndex]

  detail = detail.strip()
  if len(detail) > MAX_DETAIL_LENGTH:
    detail = detail[:MAX_DETAIL_LENGTH] + "…"
  return detail


def errorHintFor(errorOutput: str) -> str:
  """yt-dlp のエラー内容から，利用者が取るべき対処方法を選ぶ."""
  loweredOutput = errorOutput.lower()
  for keyword, hint in YTDLP_ERROR_HINTS:
    if keyword in loweredOutput:
      return hint
  return DEFAULT_ERROR_HINT


def fetchMetadata(
  url: str, quality: str | None, cookies: AccessOptions | None = None
) -> dict[str, Any]:
  """URLの動画情報をJSONとして取得する."""
  cookieArguments = cookies.toArguments() if cookies is not None else []
  completed = runYtdlp(
    [
      "--no-playlist",
      "--no-progress",
      "--no-warnings",
      *jsRuntimeArguments(),
      "-f",
      formatSelector(quality),
      *cookieArguments,
      "-J",
      url,
    ],
    METADATA_TIMEOUT,
  )

  try:
    return json.loads(completed.stdout)
  except json.JSONDecodeError as error:
    raise SourceError(
      "yt-dlp の応答を解釈できません．",
      hint="`yt-dlp -U` で yt-dlp を更新してください．",
    ) from error


def extractStreamUrl(metadata: dict[str, Any]) -> str:
  """動画情報から，直接再生できるURLを取り出す."""
  streamUrl = metadata.get("url")
  if not streamUrl:
    # 新しい yt-dlp では選択結果が requested_downloads に入る
    downloads = metadata.get("requested_downloads") or []
    if downloads:
      streamUrl = downloads[0].get("url")

  if not streamUrl:
    raise SourceError(
      "映像と音声が一体になった形式が見つかりませんでした．",
      hint="`--cache` を付けてダウンロードしてから再生してください．",
    )
  return str(streamUrl)


def _sanitizeIdentifier(value: str, fallback: str, maxLength: int) -> str:
  """ファイル名の一部として安全に使える文字列へ変換する."""
  safeValue = "".join(
    character for character in value if character.isalnum() or character in "-_"
  )
  return safeValue[:maxLength] if safeValue else fallback


def _sanitizeExtension(value: str) -> str:
  """拡張子として安全な英数字のみを残す."""
  safeValue = "".join(character for character in value if character.isalnum())
  return safeValue[:MAX_EXTENSION_LENGTH].lower() if safeValue else DEFAULT_EXTENSION


def cacheKeyFor(metadata: dict[str, Any], url: str, quality: str | None) -> str:
  """URL・画質・動画IDから，衝突しないキャッシュ名を組み立てる."""
  extractor = _sanitizeIdentifier(
    str(metadata.get("extractor_key") or metadata.get("extractor") or "site"),
    "site",
    MAX_ID_LENGTH,
  )
  videoId = _sanitizeIdentifier(str(metadata.get("id") or ""), "video", MAX_ID_LENGTH)
  qualityLabel = _sanitizeIdentifier(
    str(quality or config.DEFAULT_QUALITY), "auto", MAX_ID_LENGTH
  )
  # 同じ動画IDでもURLが異なる場合に取り違えないよう，URLの要約を付ける
  urlDigest = hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:URL_DIGEST_LENGTH]
  return f"{extractor}-{videoId}-{qualityLabel}-{urlDigest}"


def cachePathFor(
  metadata: dict[str, Any], url: str = "", quality: str | None = None
) -> Path:
  """動画情報から，キャッシュファイルの保存先を組み立てる.

  外部から渡される値をそのまま連結すると，キャッシュディレクトリの外へ
  書き出せてしまうため，構成要素を無害化したうえで保存先を検証する.
  """
  extension = _sanitizeExtension(str(metadata.get("ext") or ""))
  cacheDirectory = config.cacheDir()
  candidate = cacheDirectory / f"{cacheKeyFor(metadata, url, quality)}.{extension}"

  # 念のため，解決後もキャッシュディレクトリ配下であることを確認する
  resolvedDirectory = cacheDirectory.expanduser().resolve()
  resolvedCandidate = candidate.expanduser().resolve()
  if resolvedDirectory not in resolvedCandidate.parents:
    raise SourceError(
      "キャッシュの保存先を決められません．",
      hint=f"保存先は {cacheDirectory} の中である必要があります．",
    )

  return candidate


def downloadToCache(
  url: str,
  quality: str | None,
  targetPath: Path,
  notify: NotifyFunction | None = None,
  cookies: AccessOptions | None = None,
) -> Path:
  """動画をキャッシュディレクトリへ保存する．既にあれば再利用する."""
  if isUsableCache(targetPath):
    if notify is not None:
      notify(f"キャッシュを使用します: {targetPath}")
    return targetPath

  # 前回の失敗で残った中途半端なファイルは作り直す
  removeQuietly(targetPath)

  try:
    targetPath.parent.mkdir(parents=True, exist_ok=True)
  except OSError as error:
    raise SourceError(
      f"キャッシュディレクトリを作成できません: {targetPath.parent}（{error}）"
    ) from error

  if notify is not None:
    notify("動画をダウンロードしています．しばらくお待ちください．")

  # 途中で失敗したファイルを完成品と取り違えないよう，別名で受け取る
  partialPath = targetPath.with_name(targetPath.name + PARTIAL_SUFFIX)
  removeQuietly(partialPath)

  cookieArguments = cookies.toArguments() if cookies is not None else []
  try:
    runYtdlp(
      [
        "--no-playlist",
        "--no-progress",
        "--no-warnings",
        *jsRuntimeArguments(),
        "-f",
        formatSelector(quality),
        *cookieArguments,
        "-o",
        str(partialPath),
        url,
      ],
      DOWNLOAD_TIMEOUT,
    )
  except SourceError:
    removeQuietly(partialPath)
    raise

  if not isUsableCache(partialPath):
    fileSize = partialPath.stat().st_size if partialPath.is_file() else 0
    removeQuietly(partialPath)
    raise SourceError(
      f"ダウンロードした動画が不完全です（{fileSize}バイト）．",
      hint="通信状況を確認して，もう一度お試しください．",
    )

  try:
    os.replace(partialPath, targetPath)
  except OSError as error:
    removeQuietly(partialPath)
    raise SourceError(f"キャッシュを保存できません: {targetPath}（{error}）") from error

  return targetPath


def isUsableCache(path: Path) -> bool:
  """キャッシュとして再利用できるファイルかどうかを判定する."""
  try:
    return path.is_file() and path.stat().st_size >= MIN_CACHE_FILE_SIZE
  except OSError:
    return False


def removeQuietly(path: Path) -> None:
  """ファイルが残っていれば削除する（失敗しても無視する）."""
  try:
    path.unlink(missing_ok=True)
  except OSError:
    pass


def resolveUrl(
  url: str,
  quality: str | None = None,
  useCache: bool = False,
  notify: NotifyFunction | None = None,
  cookies: AccessOptions | None = None,
) -> PlayableSource:
  """URLを再生可能な入力へ解決する."""
  normalizedUrl = url.strip()
  cookieOptions = cookies if cookies is not None else AccessOptions.resolve()

  if notify is not None:
    notify("動画の情報を取得しています．")

  metadata = fetchMetadata(normalizedUrl, quality, cookieOptions)
  title = str(metadata.get("title") or normalizedUrl)
  duration = metadata.get("duration")
  durationSeconds = float(duration) if isinstance(duration, (int, float)) else None

  if useCache:
    cachedFile = downloadToCache(
      normalizedUrl,
      quality,
      cachePathFor(metadata, normalizedUrl, quality),
      notify,
      cookieOptions,
    )
    return PlayableSource(
      path=str(cachedFile), title=title, duration=durationSeconds, isRemote=False
    )

  if metadata.get("is_live"):
    if notify is not None:
      notify("ライブ配信のため，再生時間は表示されません．")

  return PlayableSource(
    path=extractStreamUrl(metadata),
    title=title,
    duration=durationSeconds,
    isRemote=True,
  )


def openSource(
  pathOrUrl: str,
  quality: str | None = None,
  useCache: bool = False,
  notify: NotifyFunction | None = None,
  cookies: AccessOptions | None = None,
) -> PlayableSource:
  """動画ファイルまたはURLを，再生可能な入力へ解決する."""
  if isUrl(pathOrUrl):
    return resolveUrl(pathOrUrl, quality, useCache, notify, cookies)

  resolvedPath = resolveVideoPath(pathOrUrl)
  return PlayableSource(path=resolvedPath, title=Path(resolvedPath).name)


# ---------------------------------------------------------------------------
# キャッシュの管理
# ---------------------------------------------------------------------------


def cachedFiles() -> list[Path]:
  """キャッシュ済みの動画ファイルを一覧で返す."""
  cacheDirectory = config.cacheDir()
  if not cacheDirectory.is_dir():
    return []
  return sorted(path for path in cacheDirectory.iterdir() if path.is_file())


def clearCache() -> tuple[int, int]:
  """キャッシュをすべて削除し，削除した件数と合計サイズを返す."""
  removedCount = 0
  removedSize = 0

  for filePath in cachedFiles():
    try:
      fileSize = filePath.stat().st_size
      filePath.unlink()
    except OSError as error:
      raise SourceError(f"キャッシュを削除できません: {filePath}（{error}）") from error
    removedCount += 1
    removedSize += fileSize

  return removedCount, removedSize
