#!/bin/bash
# Sets up what PAL 286 (the lobby greeter) needs beyond the packages
# install.sh adds, on the Pi:
#   - the face models (OpenCV Zoo: YuNet finds faces, SFace tells them apart)
#   - Whisper's tiny English model, for understanding speech on the Pi, and
#     its multilingual twin, for when someone asks PAL to speak another language
#   - whisper.cpp v1.9.4, built on the Pi with the Pi 3's NEON maths turned
#     on (Raspbian's own builds leave it off). Takes about 15 minutes, once.
# Every download is checked against the checksum below. Safe to re-run.
# Usage: ./fetch-pal.sh [ssh-host]
set -euo pipefail
host=${1:-pizero}

ssh "$host" 'sudo bash -s' <<'REMOTE'
set -euo pipefail
models=/var/lib/compaq/pal-models
install -d -m 755 "$models"

fetch() {   # file url sha256
  local file=$1 url=$2 sum=$3
  if [ -f "$models/$file" ] && echo "$sum  $models/$file" | sha256sum -c --quiet 2>/dev/null; then
    echo "  have $file"
    return
  fi
  echo "  downloading $file"
  curl -fsSL -o "$models/$file.part" "$url"
  echo "$sum  $models/$file.part" | sha256sum -c --quiet
  mv "$models/$file.part" "$models/$file"
}

zoo=https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models
fetch face_detection_yunet_2023mar.onnx \
  "$zoo/face_detection_yunet/face_detection_yunet_2023mar.onnx" \
  8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4
fetch face_recognition_sface_2021dec_int8.onnx \
  "$zoo/face_recognition_sface/face_recognition_sface_2021dec_int8.onnx" \
  2b0e941e6f16cc048c20aee0c8e31f569118f65d702914540f7bfdc14048d78a
fetch ggml-tiny.en-q8_0.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en-q8_0.bin \
  5bc2b3860aa151a4c6e7bb095e1fcce7cf12c7b020ca08dcec0c6d018bb7dd94
# For other languages, when someone asks PAL to speak one (see senses.py).
fetch ggml-tiny-q8_0.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny-q8_0.bin \
  c2085835d3f50733e2ff6e4b41ae8a2b8d8110461e18821b09a15c40c42d1cca

if [ -x /opt/compaq-pal/bin/whisper-server ]; then
  echo "  have whisper-server"
else
  echo "  building whisper.cpp (about 15 minutes)"
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
    build-essential cmake git >/dev/null
  # A fresh private folder (no other account can swap files in during the
  # build), and the exact v1.9.4 commit.
  build=$(mktemp -d /var/tmp/whisper.XXXXXX)
  trap 'rm -rf "$build"' EXIT
  git clone -q --depth 1 --branch v1.9.4 https://github.com/ggml-org/whisper.cpp.git "$build"
  [ "$(git -C "$build" rev-parse HEAD)" = 927cfce34f31707e17f2bff35c349632fb9e2c3a ] ||
    { echo "whisper.cpp v1.9.4 isn't the commit it should be; stopping." >&2; exit 1; }
  flags="-mcpu=cortex-a53 -mfpu=neon-fp-armv8 -mfloat-abi=hard"
  cmake -S "$build" -B "$build/build" -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF \
    -DBUILD_SHARED_LIBS=OFF -DWHISPER_BUILD_TESTS=OFF -DWHISPER_SDL2=OFF \
    -DCMAKE_C_FLAGS="$flags" -DCMAKE_CXX_FLAGS="$flags" >/dev/null
  cmake --build "$build/build" -j3 --target whisper-server >/dev/null
  install -D -m 755 "$build/build/bin/whisper-server" /opt/compaq-pal/bin/whisper-server
  rm -rf "$build"
fi
systemctl try-restart compaq-pal.service 2>/dev/null || true
echo "PAL's models and speech engine are ready."
REMOTE
