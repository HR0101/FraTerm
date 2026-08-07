"""ハーフブロック描画のPython実装とC拡張を比較する簡易ベンチマーク."""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable

import numpy as np

from fraterm import renderer


def measure(function: Callable[[], str], iterations: int) -> float:
  """指定した関数の1回あたりの実行時間をミリ秒で返す."""
  for _ in range(3):
    function()
  started = time.perf_counter()
  for _ in range(iterations):
    function()
  return (time.perf_counter() - started) * 1000.0 / iterations


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--columns", type=int, default=120)
  parser.add_argument("--rows", type=int, default=34)
  parser.add_argument("--iterations", type=int, default=200)
  args = parser.parse_args()

  randomGenerator = np.random.default_rng(11)
  smallFrame = randomGenerator.integers(
    0,
    256,
    size=(args.rows * 2, args.columns, 3),
    dtype=np.uint8,
  )
  pythonMilliseconds = measure(
    lambda: renderer._renderHalfBlockPython(smallFrame), args.iterations
  )
  print(f"Python: {pythonMilliseconds:.3f} ms/frame")

  if renderer._native is None:
    print("Native: unavailable（Pythonフォールバックを使用）")
    return 0

  nativeMilliseconds = measure(
    lambda: renderer._native.renderHalfBlock(smallFrame), args.iterations
  )
  print(f"Native: {nativeMilliseconds:.3f} ms/frame")
  print(f"Speedup: {pythonMilliseconds / nativeMilliseconds:.2f}x")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
