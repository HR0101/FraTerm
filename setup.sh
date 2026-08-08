#!/usr/bin/env bash
#
# FraTerm の実行に必要なものを一括で用意するスクリプト．
# git clone した直後に ./setup.sh を実行すれば，仮想環境の作成から
# 依存ライブラリの導入，動作確認までを一度に行う．
#
set -euo pipefail

# 仮想環境を作る場所（リポジトリ内）
VENV_DIR=".venv"

# 必要な Python の最低バージョン
REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=10

# コマンドを置くディレクトリ（--link 指定時）
LINK_DIR="${HOME}/.local/bin"

# 実行オプション
installTools=false
installDev=false
createLink=false

scriptDir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# 表示用の関数
# ---------------------------------------------------------------------------

info() { printf '\033[1m==>\033[0m %s\n' "${1}"; }
note() { printf '    %s\n' "${1}"; }
warn() { printf '\033[33m警告:\033[0m %s\n' "${1}" >&2; }
fail() { printf '\033[31mエラー:\033[0m %s\n' "${1}" >&2; exit 1; }

usage() {
  cat <<'USAGE'
FraTerm セットアップスクリプト

使い方:
  ./setup.sh [オプション]

オプション:
  --with-tools   ffmpeg と Deno も自動で導入する（Homebrew / apt / dnf を使用）
  --dev          テスト用のライブラリ（pytest 等）も導入する
  --link         fraterm と ft を ~/.local/bin から使えるようにする
  --all          --with-tools --dev --link をまとめて指定する
  -h, --help     この説明を表示する

例:
  ./setup.sh                   最低限（Python の依存関係のみ）
  ./setup.sh --all             外部ツールとコマンド登録まで一括で行う
USAGE
}

# ---------------------------------------------------------------------------
# 引数の解析
# ---------------------------------------------------------------------------

while [ $# -gt 0 ]; do
  case "${1}" in
    --with-tools) installTools=true ;;
    --dev) installDev=true ;;
    --link) createLink=true ;;
    --all) installTools=true; installDev=true; createLink=true ;;
    -h|--help) usage; exit 0 ;;
    *) fail "不明なオプションです: ${1}（--help で一覧を表示します）" ;;
  esac
  shift
done

cd "${scriptDir}"

# ---------------------------------------------------------------------------
# 1. Python の確認
# ---------------------------------------------------------------------------

info "Python を確認しています"

pythonCommand=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "${candidate}" >/dev/null 2>&1; then
    if "${candidate}" -c "import sys; sys.exit(0 if sys.version_info >= (${REQUIRED_PYTHON_MAJOR}, ${REQUIRED_PYTHON_MINOR}) else 1)"; then
      pythonCommand="${candidate}"
      break
    fi
  fi
done

if [ -z "${pythonCommand}" ]; then
  fail "Python ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR} 以上が必要です．https://www.python.org/ から導入してください．"
fi
note "$("${pythonCommand}" --version) を使用します"

# ---------------------------------------------------------------------------
# 2. 仮想環境の作成
# ---------------------------------------------------------------------------

if [ -d "${VENV_DIR}" ]; then
  info "既存の仮想環境を使用します（${VENV_DIR}）"
else
  info "仮想環境を作成しています（${VENV_DIR}）"
  "${pythonCommand}" -m venv "${VENV_DIR}" || fail "仮想環境を作成できませんでした．"
fi

venvPython="${VENV_DIR}/bin/python"
[ -x "${venvPython}" ] || venvPython="${VENV_DIR}/Scripts/python.exe"  # Windows 向け
[ -x "${venvPython}" ] || fail "仮想環境の Python が見つかりません．${VENV_DIR} を削除して再実行してください．"

# ---------------------------------------------------------------------------
# 3. Python の依存関係
# ---------------------------------------------------------------------------

info "依存ライブラリを導入しています（数分かかることがあります）"
"${venvPython}" -m pip install --quiet --upgrade pip || warn "pip の更新に失敗しました（続行します）"

extras="youtube"
if [ "${installDev}" = true ]; then
  extras="youtube,dev"
fi

# -e で導入すると，C 拡張のビルドと本体の登録が同時に行われる
"${venvPython}" -m pip install --quiet -e ".[${extras}]" \
  || fail "依存ライブラリの導入に失敗しました．上の出力を確認してください．"
note "opencv-python，numpy，yt-dlp を導入しました"

# ---------------------------------------------------------------------------
# 4. 外部ツール（任意）
# ---------------------------------------------------------------------------

packageManager=""
if command -v brew >/dev/null 2>&1; then
  packageManager="brew"
elif command -v apt >/dev/null 2>&1; then
  packageManager="apt"
elif command -v dnf >/dev/null 2>&1; then
  packageManager="dnf"
fi

installPackage() {
  # $1: Homebrew での名前，$2: apt/dnf での名前
  case "${packageManager}" in
    brew) brew install "${1}" ;;
    apt) sudo apt install -y "$2" ;;
    dnf) sudo dnf install -y "$2" ;;
    *) return 1 ;;
  esac
}

missingTools=()

if ! command -v ffplay >/dev/null 2>&1; then
  if [ "${installTools}" = true ] && [ -n "${packageManager}" ]; then
    info "ffmpeg を導入しています（音声再生に使用）"
    installPackage ffmpeg ffmpeg || warn "ffmpeg の導入に失敗しました．"
  else
    missingTools+=("ffmpeg（--audio での音声再生に必要）")
  fi
fi

if ! command -v deno >/dev/null 2>&1 && ! command -v node >/dev/null 2>&1; then
  if [ "${installTools}" = true ] && [ -n "${packageManager}" ]; then
    info "Deno を導入しています（YouTube の取得に使用）"
    installPackage deno deno || warn "Deno の導入に失敗しました．"
  else
    missingTools+=("Deno または Node.js 22以上（YouTube の再生に必要）")
  fi
fi

# ---------------------------------------------------------------------------
# 5. コマンドの登録（任意）
# ---------------------------------------------------------------------------

if [ "${createLink}" = true ]; then
  info "コマンドを ${LINK_DIR} へ登録しています"
  mkdir -p "${LINK_DIR}"
  for commandName in fraterm ft; do
    if [ -x "${scriptDir}/${VENV_DIR}/bin/${commandName}" ]; then
      ln -sf "${scriptDir}/${VENV_DIR}/bin/${commandName}" "${LINK_DIR}/${commandName}"
      note "${LINK_DIR}/${commandName} を作成しました"
    fi
  done
  case ":${PATH}:" in
    *":${LINK_DIR}:"*) ;;
    *) warn "${LINK_DIR} が PATH に含まれていません．次の行を ~/.zshrc へ追加してください．
    export PATH=\"\${HOME}/.local/bin:\${PATH}\"" ;;
  esac
fi

# ---------------------------------------------------------------------------
# 6. 動作確認
# ---------------------------------------------------------------------------

info "動作環境を確認しています"
"${venvPython}" - <<'PYTHON'
from fraterm import diagnostics

for item in diagnostics.collect():
  print(f"    {item.statusMark()} {item.label}: {item.detail}")
  if item.hint:
    print(f"        → {item.hint}")
PYTHON

echo
info "準備ができました"

if [ ${#missingTools[@]} -gt 0 ]; then
  warn "次のツールは未導入です（無くても基本の再生はできます）"
  for tool in "${missingTools[@]}"; do
    note "・${tool}"
  done
  note "まとめて導入するには ./setup.sh --with-tools を実行してください"
  echo
fi

if [ "${createLink}" = true ]; then
  note "使い方: ft menu"
else
  note "使い方: ${VENV_DIR}/bin/ft menu"
  note "どこからでも使うには ./setup.sh --link を実行してください"
fi
