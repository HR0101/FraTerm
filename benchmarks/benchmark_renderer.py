"""ハーフブロック描画のPython実装とC拡張を比較する簡易ベンチマーク."""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable

import cv2
import numpy as np

from fraterm import config, renderer


def measure(function: Callable[[], str], iterations: int) -> float:
  """指定した関数の1回あたりの実行時間をミリ秒で返す."""
  for _ in range(3):
    function()
  started = time.perf_counter()
  for _ in range(iterations):
    function()
  return (time.perf_counter() - started) * 1000.0 / iterations


def printComparison(
  label: str,
  legacyFunction: Callable[[], str],
  optimizedFunction: Callable[[], str],
  iterations: int,
) -> None:
  """従来実装と最適化実装の時間および高速化率を表示する."""
  legacyMilliseconds = measure(legacyFunction, iterations)
  optimizedMilliseconds = measure(optimizedFunction, iterations)
  print(
    f"{label}: {legacyMilliseconds:.3f} → {optimizedMilliseconds:.3f} ms/frame "
    f"({legacyMilliseconds / optimizedMilliseconds:.2f}x)"
  )


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--columns", type=int, default=120)
  parser.add_argument("--rows", type=int, default=34)
  parser.add_argument("--iterations", type=int, default=100)
  args = parser.parse_args()

  randomGenerator = np.random.default_rng(11)
  sourceFrame = randomGenerator.integers(
    0,
    256,
    size=(1080, 1920, 3),
    dtype=np.uint8,
  )
  sourceFrame = cv2.GaussianBlur(sourceFrame, (0, 0), 4)
  smallFrame = cv2.resize(
    sourceFrame,
    (args.columns, args.rows * 2),
    interpolation=cv2.INTER_LINEAR,
  )
  pythonMilliseconds = measure(
    lambda: renderer._renderHalfBlockPython(smallFrame), args.iterations
  )
  print(f"ANSI Python: {pythonMilliseconds:.3f} ms/frame")

  if renderer._native is None:
    print("ANSI Native: unavailable（Pythonフォールバックを使用）")
  else:
    nativeMilliseconds = measure(
      lambda: renderer._native.renderHalfBlock(smallFrame), args.iterations
    )
    print(f"ANSI Native: {nativeMilliseconds:.3f} ms/frame")
    print(f"ANSI speedup: {pythonMilliseconds / nativeMilliseconds:.2f}x")

  def legacyAscii() -> str:
    grayFrame = cv2.cvtColor(sourceFrame, cv2.COLOR_BGR2GRAY)
    resizedFrame = cv2.resize(
      grayFrame,
      (args.columns, args.rows),
      interpolation=cv2.INTER_AREA,
    )
    return renderer._renderAsciiPython(resizedFrame, config.DEFAULT_CHARSET)

  def legacyColor() -> str:
    resizedFrame = cv2.resize(
      sourceFrame,
      (args.columns, args.rows * 2),
      interpolation=cv2.INTER_AREA,
    )
    return renderer._renderHalfBlockPython(resizedFrame)

  def legacyMono() -> str:
    resizedFrame = cv2.resize(
      sourceFrame,
      (args.columns, args.rows * 2),
      interpolation=cv2.INTER_AREA,
    )
    grayFrame = cv2.cvtColor(resizedFrame, cv2.COLOR_BGR2GRAY)
    colorFrame = cv2.cvtColor(grayFrame, cv2.COLOR_GRAY2BGR)
    return renderer._renderHalfBlockPython(colorFrame)

  printComparison(
    "ASCII pipeline",
    legacyAscii,
    lambda: renderer.renderAscii(sourceFrame, args.columns, args.rows),
    args.iterations,
  )
  printComparison(
    "Color pipeline",
    legacyColor,
    lambda: renderer.renderHalfBlock(sourceFrame, args.columns, args.rows),
    args.iterations,
  )
  printComparison(
    "Mono pipeline",
    legacyMono,
    lambda: renderer.renderHalfBlock(
      sourceFrame, args.columns, args.rows, grayscale=True
    ),
    args.iterations,
  )
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
