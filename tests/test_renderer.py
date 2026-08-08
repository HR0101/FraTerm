"""フレーム変換処理に関するテスト."""

from __future__ import annotations

import re

import numpy as np
import pytest

from fraterm import config, renderer
from fraterm.errors import PlaybackError

# 24bitカラー指定を取り出す正規表現
FOREGROUND_PATTERN = re.compile(r"38;2;(\d+);(\d+);(\d+)")


def makeFrame(width: int, height: int, value: int = 0) -> np.ndarray:
  """単色のBGRフレームを作る."""
  return np.full((height, width, 3), value, dtype=np.uint8)


def test_computeSizeKeepsAspectRatio():
  """文字セルの縦横比を考慮して行数が決まることを確認する."""
  columns, rows = renderer.computeSize(1920, 1080, 100, 40)
  assert columns == 100
  assert rows == round(100 * (1080 / 1920) / config.CELL_ASPECT_RATIO)


def test_computeSizeFitsInTerminalHeight():
  """縦に収まらない場合は行数を基準に列数が計算されることを確認する."""
  terminalHeight = 10
  columns, rows = renderer.computeSize(1920, 1080, 200, terminalHeight)
  assert rows == terminalHeight - config.STATUS_ROW_COUNT
  assert columns <= 200


def test_computeSizeRespectsMaxWidth():
  """--width 指定が上限として働くことを確認する."""
  columns, _ = renderer.computeSize(1920, 1080, 200, 60, maxWidth=40)
  assert columns == 40


def test_computeSizeRejectsEmptyFrame():
  """フレームサイズが不正な場合にエラーになることを確認する."""
  with pytest.raises(PlaybackError):
    renderer.computeSize(0, 0, 80, 24)


def test_pixelHeightForModes():
  """ハーフブロックのモードでは縦方向に2倍の画素を使うことを確認する."""
  assert renderer.pixelHeightFor(10, config.MODE_ASCII) == 10
  assert renderer.pixelHeightFor(10, config.MODE_COLOR) == 20
  assert renderer.pixelHeightFor(10, config.MODE_MONO) == 20


def test_renderAsciiHasRequestedShape():
  """ASCII描画が指定した行数・列数になることを確認する."""
  output = renderer.renderAscii(makeFrame(64, 48, 128), 20, 8)
  lines = output.split("\n")
  assert len(lines) == 8
  assert all(len(line) == 20 for line in lines)


def test_renderAsciiMapsBrightnessToCharset():
  """暗い画素と明るい画素が文字セットの両端へ対応することを確認する."""
  charset = " .:-=+*#%@"

  darkOutput = renderer.renderAscii(makeFrame(16, 16, 0), 8, 4, charset)
  assert set(darkOutput.replace("\n", "")) == {charset[0]}

  brightOutput = renderer.renderAscii(makeFrame(16, 16, 255), 8, 4, charset)
  assert set(brightOutput.replace("\n", "")) == {charset[-1]}


def test_renderAsciiWithSingleCharacterCharset():
  """1文字だけの文字セットでも例外にならないことを確認する."""
  output = renderer.renderAscii(makeFrame(16, 16, 128), 4, 2, "#")
  assert output.split("\n") == ["####", "####"]


def test_renderAsciiBrightnessRaisesValues():
  """明るさ補正が出力を明るい側の文字へ寄せることを確認する."""
  charset = " .:-=+*#%@"
  baseOutput = renderer.renderAscii(makeFrame(16, 16, 100), 4, 2, charset)
  brightOutput = renderer.renderAscii(
    makeFrame(16, 16, 100), 4, 2, charset, brightness=0.5
  )
  assert charset.index(brightOutput[0]) > charset.index(baseOutput[0])


def test_renderAsciiFallbackMatchesSelectedRenderer(monkeypatch):
  """ASCIIのPythonフォールバックが選択中の実装と同じ結果を返すことを確認する."""
  frame = np.arange(12 * 16 * 3, dtype=np.uint8).reshape(12, 16, 3)
  expected = renderer.renderAscii(
    frame, 7, 3, config.CHARSET_PRESETS["blocks"], 0.2, 1.4
  )

  monkeypatch.setattr(renderer, "_native", None)
  assert renderer.renderAscii(
    frame, 7, 3, config.CHARSET_PRESETS["blocks"], 0.2, 1.4
  ) == expected


@pytest.mark.skipif(
  renderer._native is None, reason="任意のC拡張がビルドされていません"
)
@pytest.mark.parametrize(
  "charset",
  [config.DEFAULT_CHARSET, config.CHARSET_PRESETS["blocks"], "#", " 🌑🌕"],
)
def test_nativeAsciiMatchesPythonFallback(charset):
  """ASCIIのC拡張とPython実装がUnicodeを含め同じ結果を返すことを確認する."""
  grayFrame = np.arange(9 * 13, dtype=np.uint8).reshape(9, 13)[:, ::-1]
  assert renderer._native.renderAscii(grayFrame, charset) == (
    renderer._renderAsciiPython(grayFrame, charset)
  )


@pytest.mark.skipif(
  renderer._native is None, reason="任意のC拡張がビルドされていません"
)
def test_nativeAsciiRejectsInvalidFrameShape():
  """ASCIIのC拡張がカラー配列を安全に拒否することを確認する."""
  with pytest.raises(ValueError):
    renderer._native.renderAscii(np.zeros((4, 4, 3), dtype=np.uint8), " .")


def test_renderHalfBlockUsesBlockCharacters():
  """カラー描画がハーフブロック文字とANSIコードを含むことを確認する."""
  frame = makeFrame(32, 32, 200)
  output = renderer.renderHalfBlock(frame, 10, 4)
  lines = output.split("\n")

  assert len(lines) == 4
  assert all(line.count(renderer.UPPER_HALF_BLOCK) == 10 for line in lines)
  assert all(line.startswith(renderer.ESC) for line in lines)
  assert all(line.endswith(renderer.RESET) for line in lines)


def test_renderHalfBlockOmitsRepeatedColorCodes():
  """同じ色が続く場合にANSIコードが省略されることを確認する."""
  output = renderer.renderHalfBlock(makeFrame(32, 32, 128), 20, 2)
  # 単色フレームなら，色指定は行の先頭のみで済む
  assert output.split("\n")[0].count("38;2;") == 1


def test_renderHalfBlockFallbackMatchesSelectedRenderer(monkeypatch):
  """Pythonフォールバックが選択中の描画実装と同じ結果を返すことを確認する."""
  frame = np.arange(12 * 16 * 3, dtype=np.uint8).reshape(12, 16, 3)
  expected = renderer.renderHalfBlock(
    frame, 7, 3, brightness=0.2, contrast=1.4
  )

  monkeypatch.setattr(renderer, "_native", None)
  assert renderer.renderHalfBlock(
    frame, 7, 3, brightness=0.2, contrast=1.4
  ) == expected


@pytest.mark.skipif(
  renderer._native is None, reason="任意のC拡張がビルドされていません"
)
@pytest.mark.parametrize("grayscale", [False, True])
def test_nativeRendererMatchesPythonFallback(grayscale):
  """C拡張とPython実装のANSI出力がバイト単位で一致することを確認する."""
  frame = np.arange(18 * 20 * 3, dtype=np.uint8).reshape(18, 20, 3)
  colorFrame = frame
  if grayscale:
    import cv2

    grayFrame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    colorFrame = cv2.cvtColor(grayFrame, cv2.COLOR_GRAY2BGR)

  assert renderer._native.renderHalfBlock(colorFrame) == (
    renderer._renderHalfBlockPython(colorFrame)
  )


@pytest.mark.skipif(
  renderer._native is None, reason="任意のC拡張がビルドされていません"
)
def test_nativeRendererAcceptsGrayscaleFrame():
  """モノクロ用の2次元画像をC拡張が直接描画できることを確認する."""
  grayFrame = np.arange(12 * 10, dtype=np.uint8).reshape(12, 10)
  colorFrame = np.repeat(grayFrame[:, :, None], 3, axis=2)
  assert renderer._native.renderHalfBlock(grayFrame) == (
    renderer._renderHalfBlockPython(colorFrame)
  )


@pytest.mark.skipif(
  renderer._native is None, reason="任意のC拡張がビルドされていません"
)
def test_nativeRendererAcceptsNonContiguousFrame():
  """C拡張が負のstrideを持つ画像も正しく読み取ることを確認する."""
  frame = np.arange(12 * 10 * 3, dtype=np.uint8).reshape(12, 10, 3)
  reversedFrame = frame[:, ::-1, :]
  assert renderer._native.renderHalfBlock(reversedFrame) == (
    renderer._renderHalfBlockPython(reversedFrame)
  )


@pytest.mark.skipif(
  renderer._native is None, reason="任意のC拡張がビルドされていません"
)
def test_nativeRendererRejectsInvalidFrameShape():
  """C拡張が不正な配列を安全に拒否することを確認する."""
  with pytest.raises(ValueError):
    renderer._native.renderHalfBlock(np.zeros((4, 4, 4), dtype=np.uint8))


def test_renderMonoProducesGrayColors():
  """monoモードの出力が白黒（RGBが同じ値）になることを確認する."""
  frame = np.zeros((16, 16, 3), dtype=np.uint8)
  frame[:, :, 0] = 200  # 青成分のみを強くする
  output = renderer.renderHalfBlock(frame, 8, 2, grayscale=True)

  matches = FOREGROUND_PATTERN.findall(output)
  assert matches
  assert all(red == green == blue for red, green, blue in matches)


def makeStripedFrame(width: int, height: int) -> np.ndarray:
  """縦方向にはっきりした境界を持つフレームを作る."""
  frame = np.zeros((height, width, 3), dtype=np.uint8)
  frame[:, width // 2 :] = 255
  return frame


def test_renderEdgeHasRequestedShape():
  """輪郭描画が指定した行数・列数になることを確認する."""
  output = renderer.renderEdge(makeStripedFrame(96, 96), 24, 8)
  lines = output.split("\n")
  assert len(lines) == 8
  assert all(len(line) == 24 for line in lines)


def test_renderEdgeDetectsVerticalBoundary():
  """縦の境界が縦線の記号で描かれることを確認する."""
  output = renderer.renderEdge(makeStripedFrame(96, 96), 24, 8)
  lines = output.split("\n")

  # 境界のある中央付近の列に縦線が現れる
  middleColumns = [line[11:13] for line in lines]
  assert any("|" in columns for columns in middleColumns)


def test_renderEdgeDetectsHorizontalBoundary():
  """横の境界が横線の記号で描かれることを確認する."""
  frame = np.zeros((96, 96, 3), dtype=np.uint8)
  frame[48:, :] = 255
  output = renderer.renderEdge(frame, 24, 8)
  assert "-" in output


def test_renderEdgeUsesFillWhereFlat():
  """平坦な部分は明るさに応じた文字で塗られることを確認する."""
  output = renderer.renderEdge(makeFrame(64, 64, 0), 16, 4, " .:")
  assert set(output.replace("\n", "")) == {" "}


def test_renderEdgeIsMonochrome():
  """輪郭モードがANSIカラーを含まないことを確認する."""
  output = renderer.renderEdge(makeStripedFrame(96, 96), 24, 8)
  assert renderer.ESC not in output


def test_edgeModeUsesItsOwnDefaultCharset():
  """輪郭モードでは既定の塗り文字が切り替わることを確認する."""
  assert config.charsetFor(config.MODE_EDGE, None) == config.DEFAULT_EDGE_CHARSET
  assert config.charsetFor(config.MODE_ASCII, None) == config.DEFAULT_CHARSET
  # 明示的に指定した場合は，モードによらずその指定を使う
  assert config.charsetFor(config.MODE_EDGE, "simple") == config.CHARSET_PRESETS["simple"]


def test_renderFrameDispatchesByMode():
  """モードごとに適切な描画関数が呼ばれることを確認する."""
  frame = makeFrame(32, 32, 180)

  asciiOutput = renderer.renderFrame(frame, config.MODE_ASCII, 8, 2)
  assert renderer.ESC not in asciiOutput

  edgeOutput = renderer.renderFrame(makeStripedFrame(96, 96), config.MODE_EDGE, 24, 8)
  assert renderer.ESC not in edgeOutput
  assert any(character in edgeOutput for character in renderer.EDGE_CHARACTERS)

  colorOutput = renderer.renderFrame(frame, config.MODE_COLOR, 8, 2)
  assert renderer.UPPER_HALF_BLOCK in colorOutput


def test_renderFrameRejectsUnknownMode():
  """未知のモードを指定した場合にエラーになることを確認する."""
  with pytest.raises(PlaybackError):
    renderer.renderFrame(makeFrame(8, 8), "hologram", 4, 2)


def test_renderAcceptsGrayscaleFrame():
  """グレースケール画像でも描画できることを確認する."""
  grayFrame = np.full((16, 16), 120, dtype=np.uint8)
  assert renderer.renderAscii(grayFrame, 4, 2)
  assert renderer.renderHalfBlock(grayFrame, 4, 2)


def test_supportsTrueColorDetectsColorterm(monkeypatch):
  """COLORTERM から24bitカラー対応を判定できることを確認する."""
  monkeypatch.setenv("COLORTERM", "truecolor")
  assert renderer.supportsTrueColor() is True

  monkeypatch.setenv("COLORTERM", "")
  monkeypatch.setenv("TERM", "xterm")
  monkeypatch.setenv("TERM_PROGRAM", "")
  assert renderer.supportsTrueColor() is False
