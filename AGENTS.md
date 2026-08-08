# Repository Guidelines

## Project Structure & Module Organization

FraTerm is a Python 3.10+ terminal video player. Production code lives in `fraterm/`: `cli.py` defines commands, `player.py` coordinates playback, `renderer.py` converts frames, `registry.py` persists entries, and `source.py` handles local and URL sources. Supporting terminal, audio, configuration, and error utilities are kept as focused sibling modules. Tests mirror these responsibilities under `tests/` (for example, `tests/test_renderer.py`). `README.md` is the user-facing command reference; the Japanese design documents record earlier architecture decisions.

## Build, Test, and Development Commands

Create an isolated environment and install all development extras:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run `python -m pytest` for the full suite; pytest already uses quiet output and discovers `tests/`. Use `python -m pytest tests/test_renderer.py` or `python -m pytest -k edge` for focused work. Run `python -m fraterm --help` to smoke-test the CLI, or invoke the installed `fraterm` entry point. URL playback needs `yt-dlp`; audio playback additionally needs `ffplay` from FFmpeg.

## Coding Style & Naming Conventions

Follow the existing Python style: two-space indentation, type annotations, `from __future__ import annotations`, and short module/function docstrings. Use `camelCase` for functions, methods, variables, and fixtures; `PascalCase` for classes; and `UPPER_SNAKE_CASE` for constants. Keep user-facing text and neighboring documentation in Japanese. No formatter or linter is configured, so make changes visually consistent with the surrounding module and keep imports grouped as standard library, third party, then local.

## Testing Guidelines

Use pytest functions named `test_<behavior>` and place shared fixtures in `tests/conftest.py`. Isolate configuration through the existing `isolatedHome` fixture, which sets `FRATERM_HOME`, and mock players, subprocesses, network resolution, or key input instead of relying on external services. Add regression tests for fixes and cover success paths plus user-visible failures. There is no numeric coverage gate; contributors should keep all tests passing.

## Commit & Pull Request Guidelines

History follows Conventional Commit-style subjects such as `feat: add ...`, `test: add ...`, and `docs: add ...`. Keep commits scoped and imperative. Pull requests should explain the behavior change, list verification commands, link relevant issues, and update `README.md` for CLI or configuration changes. Include terminal output or screenshots when rendering behavior changes, and call out untested OS, audio, or network-dependent behavior.

## Configuration & Safety

Never commit downloaded media, credentials, cookies, local registry files, or virtual environments. Use temporary directories and `FRATERM_HOME` in tests so development does not alter a contributor's real video registry or cache.
