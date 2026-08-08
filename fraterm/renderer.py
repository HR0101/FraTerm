"""動画フレームをターミナルへ描画する文字列に変換するモジュール."""

from __future__ import annotations

import os

import cv2
import numpy as np

from . import config
from .errors import PlaybackError

try:
  from . import _native
except ImportError:  # Cコンパイラがない環境ではPython実装へ戻す
  _native = None

ESC = "\x1b"
RESET = f"{ESC}[0m"

# 上半分のみを塗るブロック文字．前景色で上の画素，背景色で下の画素を表現する
UPPER_HALF_BLOCK = "▀"

# 輪郭の向き（輝度勾配を45度ごとに4分割したもの）に対応する文字
# 勾配と直交する方向が線の向きになるため，縦の勾配には横線を割り当てる
EDGE_CHARACTERS = ("|", "/", "-", "\\")

# 勾配の向きを4方向へ量子化する際の1区分の角度
EDGE_ANGLE_STEP = np.pi / 4.0

# 8bit値の上限
MAX_PIXEL_VALUE = 255

# xterm 256色のうち，6段階の色立方体が始まるインデックス
COLOR_CUBE_OFFSET = 16
COLOR_CUBE_STEPS = 5

# 無彩色に割り当てるグレースケール階調（232〜255）の開始位置と段数
GRAYSCALE_OFFSET = 232
GRAYSCALE_STEPS = 23

# この差以下ならグレースケール階調として扱う
GRAYSCALE_TOLERANCE = 12

# True Color対応と判断するCOLORTERMの値
TRUE_COLOR_HINTS = ("truecolor", "24bit")

# インストール時にC拡張をビルドできたかを診断やベンチマークで確認できるようにする
HAS_NATIVE_RENDERER = _native is not None


def supportsTrueColor() -> bool:
  """実行中のターミナルが24bitカラーに対応していそうかどうかを推定する."""
  colorTerm = os.environ.get("COLORTERM", "").lower()
  if any(hint in colorTerm for hint in TRUE_COLOR_HINTS):
    return True

  termName = os.environ.get("TERM", "").lower()
  if "truecolor" in termName or "direct" in termName:
    return True

  # iTerm2 や Apple Terminal など，COLORTERM を設定しない環境向けの判定
  termProgram = os.environ.get("TERM_PROGRAM", "").lower()
  return termProgram in {"iterm.app", "wezterm", "vscode", "ghostty", "hyper"}


def computeSize(
  frameWidth: int,
  frameHeight: int,
  terminalWidth: int,
  terminalHeight: int,
  maxWidth: int | None = None,
  reservedRows: int = config.STATUS_ROW_COUNT,
) -> tuple[int, int]:
  """動画とターミナルのサイズから，描画する文字数（列数・行数）を求める.

  文字セルは正方形ではないため，config.CELL_ASPECT_RATIO で高さを補正する.
  reservedRows には，ステータス行など描画に使わない行数を渡す.
  """
  if frameWidth <= 0 or frameHeight <= 0:
    raise PlaybackError("動画のフレームサイズを取得できません．")

  maxColumns = max(1, terminalWidth)
  if maxWidth is not None and maxWidth > 0:
    maxColumns = min(maxColumns, maxWidth)
  maxRows = max(1, terminalHeight - max(0, reservedRows))

  columns = maxColumns
  rows = max(1, round(columns * frameHeight / frameWidth / config.CELL_ASPECT_RATIO))

  # 高さが画面に収まらない場合は，行数を基準に列数を計算し直す
  if rows > maxRows:
    rows = maxRows
    columns = max(1, round(rows * config.CELL_ASPECT_RATIO * frameWidth / frameHeight))
    columns = min(columns, maxColumns)

  return columns, rows


def pixelHeightFor(rows: int, mode: str) -> int:
  """描画モードに応じて，サンプリングする画素の縦方向の数を返す."""
  return rows * 2 if mode in config.HALF_BLOCK_MODES else rows


def _adjust(image: np.ndarray, brightness: float, contrast: float) -> np.ndarray:
  """明るさとコントラストを補正した画像を返す."""
  if brightness == 0.0 and contrast == 1.0:
    return image

  center = (MAX_PIXEL_VALUE + 1) / 2.0
  adjusted = (image.astype(np.float32) - center) * contrast
  adjusted += center + brightness * MAX_PIXEL_VALUE
  return np.clip(adjusted, 0, MAX_PIXEL_VALUE).astype(np.uint8)


def _resize(frame: np.ndarray, columns: int, rows: int) -> np.ndarray:
  """指定した文字数に合わせてフレームを縮小・拡大する."""
  sourceHeight, sourceWidth = frame.shape[:2]
  if columns == sourceWidth and rows == sourceHeight:
    return frame
  # ターミナル表示では速度と画質のバランスが良い線形補間を使用する
  return cv2.resize(frame, (columns, rows), interpolation=cv2.INTER_LINEAR)


def toXterm256(rgbArray: np.ndarray) -> np.ndarray:
  """RGB値を xterm 256色のインデックスへ変換する."""
  values = rgbArray.astype(np.int16)
  red, green, blue = values[..., 0], values[..., 1], values[..., 2]

  def level(channel: np.ndarray, steps: int) -> np.ndarray:
    return np.clip(
      np.rint(channel.astype(np.float32) * steps / MAX_PIXEL_VALUE), 0, steps
    ).astype(np.int16)

  cubeIndex = (
    COLOR_CUBE_OFFSET
    + 36 * level(red, COLOR_CUBE_STEPS)
    + 6 * level(green, COLOR_CUBE_STEPS)
    + level(blue, COLOR_CUBE_STEPS)
  )

  # 彩度が低い画素は，色立方体よりグレースケール階調のほうが滑らかになる
  isGray = (values.max(axis=-1) - values.min(axis=-1)) <= GRAYSCALE_TOLERANCE
  grayIndex = GRAYSCALE_OFFSET + level(
    (red + green + blue) // 3, GRAYSCALE_STEPS
  )

  return np.where(isGray, grayIndex, cubeIndex)


def _colorizeLines(
  characters: np.ndarray,
  frame: np.ndarray,
  columns: int,
  rows: int,
  colorMode: str,
  brightness: float,
  contrast: float,
) -> str:
  """文字の格子に色を付けて，1つの文字列へまとめる."""
  if colorMode == config.COLOR_OFF:
    return "\n".join("".join(row) for row in characters)

  colorFrame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR) if frame.ndim == 2 else frame
  smallFrame = _adjust(_resize(colorFrame, columns, rows), brightness, contrast)
  # OpenCVはBGR順のため，RGB順へ並べ替える
  rgbFrame = smallFrame[:, :, ::-1]

  useTrueColor = colorMode == config.COLOR_TRUE
  colorValues = rgbFrame.tolist() if useTrueColor else toXterm256(rgbFrame).tolist()

  lines: list[str] = []
  for rowIndex in range(rows):
    parts: list[str] = []
    previousColor = None
    for character, color in zip(characters[rowIndex], colorValues[rowIndex]):
      # 直前のセルと同じ色ならANSIコードを省略し，出力量を減らす
      if color != previousColor:
        if useTrueColor:
          parts.append(f"{ESC}[38;2;{color[0]};{color[1]};{color[2]}m")
        else:
          parts.append(f"{ESC}[38;5;{color}m")
        previousColor = color
      parts.append(character)
    parts.append(RESET)
    lines.append("".join(parts))

  return "\n".join(lines)


def renderAscii(
  frame: np.ndarray,
  columns: int,
  rows: int,
  charset: str = config.DEFAULT_CHARSET,
  brightness: float = config.DEFAULT_BRIGHTNESS,
  contrast: float = config.DEFAULT_CONTRAST,
  colorMode: str = config.DEFAULT_COLOR,
) -> str:
  """フレームをグレースケール化し，明るさに応じたASCII文字へ変換する."""
  if not charset:
    charset = config.DEFAULT_CHARSET

  # 先に縮小してから色変換することで，大きな入力フレーム全体の変換を避ける
  smallFrame = _resize(frame, columns, rows)
  grayFrame = (
    cv2.cvtColor(smallFrame, cv2.COLOR_BGR2GRAY)
    if smallFrame.ndim == 3
    else smallFrame
  )
  grayFrame = _adjust(grayFrame, brightness, contrast)

  if colorMode == config.COLOR_OFF:
    if _native is not None:
      return _native.renderAscii(grayFrame, charset)
    return _renderAsciiPython(grayFrame, charset)

  characters = _asciiCharacterGrid(grayFrame, charset)
  return _colorizeLines(
    characters, frame, columns, rows, colorMode, brightness, contrast
  )


def _asciiCharacterGrid(grayFrame: np.ndarray, charset: str) -> np.ndarray:
  """輝度配列を文字の格子へ変換する."""
  characterTable = np.array(list(charset))
  lastIndex = len(charset) - 1
  if lastIndex <= 0:
    return np.full(grayFrame.shape, charset, dtype="<U1")

  indices = grayFrame.astype(np.uint32) * lastIndex // MAX_PIXEL_VALUE
  return characterTable[indices]


def _renderAsciiPython(grayFrame: np.ndarray, charset: str) -> str:
  """C拡張を利用できない環境向けにASCII文字列をPythonで組み立てる."""
  characters = _asciiCharacterGrid(grayFrame, charset)
  return "\n".join("".join(row) for row in characters)


def renderEdge(
  frame: np.ndarray,
  columns: int,
  rows: int,
  charset: str = config.DEFAULT_EDGE_CHARSET,
  brightness: float = config.DEFAULT_BRIGHTNESS,
  contrast: float = config.DEFAULT_CONTRAST,
  colorMode: str = config.DEFAULT_COLOR,
) -> str:
  """輪郭を検出し，線の向きに応じた記号で描画する（白黒）.

  明るさだけで文字を選ぶ方式と異なり，物の形が線として現れる.
  """
  if not charset:
    charset = config.DEFAULT_EDGE_CHARSET

  grayFrame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame

  # 1文字を複数画素で判定するため，文字数より細かい格子へ縮小する
  sampleFactor = config.EDGE_SAMPLE_FACTOR
  sampleFrame = _resize(grayFrame, columns * sampleFactor, rows * sampleFactor)
  sampleFrame = _adjust(sampleFrame, brightness, contrast)

  # 細かなノイズを線として拾わないよう，わずかにぼかす
  blurredFrame = cv2.GaussianBlur(sampleFrame, (3, 3), 0)
  gradientX = cv2.Sobel(blurredFrame, cv2.CV_32F, 1, 0, ksize=3)
  gradientY = cv2.Sobel(blurredFrame, cv2.CV_32F, 0, 1, ksize=3)

  magnitude = cv2.magnitude(gradientX, gradientY)
  angle = np.arctan2(gradientY, gradientX)
  # 180度周期のため，4方向へ丸めて剰余を取る
  directionBins = np.mod(np.rint(angle / EDGE_ANGLE_STEP), len(EDGE_CHARACTERS))
  directionBins = directionBins.astype(np.int16)

  # 映像の明暗差に合わせ，しきい値をフレームごとに決める
  threshold = max(
    config.EDGE_MIN_THRESHOLD,
    float(np.percentile(magnitude, config.EDGE_PERCENTILE)),
  )
  strongMask = magnitude >= threshold

  # 文字セルごとに，どの向きの線が最も多いかを数える
  binBlocks = directionBins.reshape(rows, sampleFactor, columns, sampleFactor)
  maskBlocks = strongMask.reshape(rows, sampleFactor, columns, sampleFactor)
  directionCounts = np.stack(
    [
      np.logical_and(maskBlocks, binBlocks == binIndex).sum(axis=(1, 3))
      for binIndex in range(len(EDGE_CHARACTERS))
    ],
    axis=-1,
  )

  dominantDirection = directionCounts.argmax(axis=-1)
  dominantCount = directionCounts.max(axis=-1)
  requiredCount = max(1, int(sampleFactor * sampleFactor * config.EDGE_MIN_RATIO))

  # 線と判定されなかったセルは，明るさに応じた文字で塗る
  cellLuminance = _adjust(_resize(grayFrame, columns, rows), brightness, contrast)
  lastIndex = max(1, len(charset) - 1)
  fillIndices = cellLuminance.astype(np.uint32) * lastIndex // MAX_PIXEL_VALUE
  fillCharacters = np.array(list(charset))[fillIndices]
  edgeCharacters = np.array(EDGE_CHARACTERS)[dominantDirection]

  characters = np.where(
    dominantCount >= requiredCount, edgeCharacters, fillCharacters
  )
  return _colorizeLines(
    characters, frame, columns, rows, colorMode, brightness, contrast
  )


def renderHalfBlock(
  frame: np.ndarray,
  columns: int,
  rows: int,
  grayscale: bool = False,
  brightness: float = config.DEFAULT_BRIGHTNESS,
  contrast: float = config.DEFAULT_CONTRAST,
) -> str:
  """ハーフブロック文字と24bitカラーで，1文字あたり上下2画素を描画する."""
  colorFrame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR) if frame.ndim == 2 else frame
  smallFrame = _resize(colorFrame, columns, rows * 2)

  if grayscale:
    smallFrame = cv2.cvtColor(smallFrame, cv2.COLOR_BGR2GRAY)

  smallFrame = _adjust(smallFrame, brightness, contrast)

  if _native is not None:
    return _native.renderHalfBlock(smallFrame)

  if grayscale:
    smallFrame = cv2.cvtColor(smallFrame, cv2.COLOR_GRAY2BGR)

  return _renderHalfBlockPython(smallFrame)


def _renderHalfBlockPython(smallFrame: np.ndarray) -> str:
  """C拡張を利用できない環境向けにANSI文字列をPythonで組み立てる."""
  rows = smallFrame.shape[0] // 2

  # OpenCVはBGR順のため，RGB順へ並べ替える
  rgbFrame = smallFrame[:, :, ::-1]
  topPixels = rgbFrame[0::2].tolist()
  bottomPixels = rgbFrame[1::2].tolist()

  lines: list[str] = []
  for rowIndex in range(rows):
    topRow = topPixels[rowIndex]
    bottomRow = bottomPixels[rowIndex]
    parts: list[str] = []
    previousTop: list[int] | None = None
    previousBottom: list[int] | None = None

    for topPixel, bottomPixel in zip(topRow, bottomRow):
      # 直前のセルと同じ色ならANSIコードを省略し，出力量を減らす
      topChanged = topPixel != previousTop
      bottomChanged = bottomPixel != previousBottom
      if topChanged and bottomChanged:
        parts.append(
          f"{ESC}[38;2;{topPixel[0]};{topPixel[1]};{topPixel[2]};"
          f"48;2;{bottomPixel[0]};{bottomPixel[1]};{bottomPixel[2]}m"
        )
      elif topChanged:
        parts.append(f"{ESC}[38;2;{topPixel[0]};{topPixel[1]};{topPixel[2]}m")
      elif bottomChanged:
        parts.append(
          f"{ESC}[48;2;{bottomPixel[0]};{bottomPixel[1]};{bottomPixel[2]}m"
        )

      parts.append(UPPER_HALF_BLOCK)
      previousTop = topPixel
      previousBottom = bottomPixel

    parts.append(RESET)
    lines.append("".join(parts))

  return "\n".join(lines)


def renderFrame(
  frame: np.ndarray,
  mode: str,
  columns: int,
  rows: int,
  charset: str | None = None,
  brightness: float = config.DEFAULT_BRIGHTNESS,
  contrast: float = config.DEFAULT_CONTRAST,
  colorMode: str = config.DEFAULT_COLOR,
) -> str:
  """描画モードに応じてフレームを文字列へ変換する.

  charset に None を渡した場合は，モードごとの既定の文字セットを使う.
  colorMode は文字で描くモード（ascii・edge）でのみ有効である.
  """
  resolvedCharset = config.charsetFor(mode, charset)

  if mode == config.MODE_ASCII:
    return renderAscii(
      frame, columns, rows, resolvedCharset, brightness, contrast, colorMode
    )
  if mode == config.MODE_EDGE:
    return renderEdge(
      frame, columns, rows, resolvedCharset, brightness, contrast, colorMode
    )
  if mode == config.MODE_COLOR:
    return renderHalfBlock(frame, columns, rows, False, brightness, contrast)
  if mode == config.MODE_MONO:
    return renderHalfBlock(frame, columns, rows, True, brightness, contrast)

  raise PlaybackError(
    f"未知の描画モードです: {mode}",
    hint=f"使用できるモード: {', '.join(config.AVAILABLE_MODES)}",
  )
