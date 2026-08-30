#!/usr/bin/env bash
set -euo pipefail

DEST="${RUNNER_TEMP:-/tmp}/sahool-actions-security-tools"
BIN_DIR="$DEST/bin"
mkdir -p "$BIN_DIR"

install_tar_tool() {
  local name="$1" repository="$2" version="$3" archive="$4" expected="$5" binary="$6"
  local url="https://github.com/${repository}/releases/download/${version}/${archive}"
  local archive_path="$DEST/$archive"
  local extract_dir="$DEST/extract-$name"
  mkdir -p "$extract_dir"
  curl --fail --silent --show-error --location --retry 3 --retry-all-errors \
    "$url" -o "$archive_path"
  echo "$expected  $archive_path" | sha256sum --check --strict -
  tar -xzf "$archive_path" -C "$extract_dir"
  test -x "$extract_dir/$binary"
  install -m 0755 "$extract_dir/$binary" "$BIN_DIR/$name"
  "$BIN_DIR/$name" --version
}

install_tar_tool actionlint rhysd/actionlint v1.7.12 \
  actionlint_1.7.12_linux_amd64.tar.gz \
  8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8 actionlint
install_tar_tool zizmor zizmorcore/zizmor v1.29.0 \
  zizmor-x86_64-unknown-linux-gnu.tar.gz \
  dd96df044a6e8538d5f423790f453bdd03d49e5b2bcc38214acc41a2f1297839 zizmor
install_tar_tool pinact suzuki-shunsuke/pinact v4.1.1 \
  pinact_linux_amd64.tar.gz \
  d1cffebe5704b74e2e5f8a864efb9f7e54768972dc686188c008033fb1797841 pinact
install_tar_tool poutine boostsecurityio/poutine v1.1.6 \
  poutine_Linux_x86_64.tar.gz \
  abde716599a65608b023a69ed9316e5f083a7bca48612151c2720835883757ea poutine

if [[ -n "${GITHUB_PATH:-}" ]]; then
  echo "$BIN_DIR" >> "$GITHUB_PATH"
else
  echo "$BIN_DIR"
fi
