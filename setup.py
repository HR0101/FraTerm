"""FraTerm の任意ネイティブ拡張を構成するビルドスクリプト."""

from setuptools import Extension, setup


setup(
  ext_modules=[
    Extension(
      "fraterm._native",
      sources=["fraterm/_native.c"],
      optional=True,
    )
  ]
)
