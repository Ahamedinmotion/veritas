#!/usr/bin/env bash
# Build the OFFLINE WINDOWS KIT ("Route C") on the Mac, for a booth laptop that cannot reach the internet.
#   ./scripts/build_winkit.sh [OUT_DIR]          default OUT_DIR: ../_usb/winkit  (outside the repo, ~1.4 GB)
# Produces:
#   OUT_DIR/site-packages/   every library for Windows x64 + Python 3.12 (CPU PyTorch), plus the VC++ runtime DLLs
#                            copied into torch\lib so no admin install is needed
#   OUT_DIR/cpython-3.12.12+20260127-x86_64-pc-windows-msvc-install_only_stripped.tar.gz
#   OUT_DIR/models/          a copy of models/ (2.4 GB incl. the face-swap detector; APFS clones, no extra Mac disk).
#                            start_windows_kit.bat uses it when C:\veritas\models is missing or has no face_swap\.
# The face-swap detector's libraries (onnxruntime, torchvision + protobuf) come from uv.lock like everything else; its
# MTCNN code is vendored in server/vendor/.
# On the laptop: copy OUT_DIR to C:\veritas\winkit, then in a Command Prompt:
#   cd C:\veritas  &&  tar -xf winkit\cpython-*.tar.gz -C winkit      (creates winkit\python\python.exe)
#   scripts\start_windows_kit.bat
# Needs internet (pypi.org, download.pytorch.org, github.com) on the Mac only.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-../_usb/winkit}"
PBS_TAG=20260127
PBS_FILE="cpython-3.12.12+${PBS_TAG}-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
MSVC_VER=14.51.36231
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"

echo "1/5  exporting the locked requirements"
uv export --locked --format requirements-txt --no-hashes --no-emit-project -o "$OUT/requirements-win.txt" >/dev/null

echo "2/5  installing Windows x64 wheels into $OUT/site-packages"
rm -rf "$OUT/site-packages"
uv pip install --python-platform x86_64-pc-windows-msvc --python-version 3.12 --target "$OUT/site-packages" \
  --index-strategy unsafe-best-match --extra-index-url https://download.pytorch.org/whl/cpu \
  -r "$OUT/requirements-win.txt"

echo "3/5  adding the Visual C++ runtime DLLs next to torch (msvc-runtime $MSVC_VER from PyPI)"
DL="$(mktemp -d)"
URL="$(python3 -I -c "
import json, sys, urllib.request
d = json.load(urllib.request.urlopen('https://pypi.org/pypi/msvc-runtime/$MSVC_VER/json'))
print([f['url'] for f in d['urls'] if f['filename'].endswith('cp312-cp312-win_amd64.whl')][0])")"
curl -fsSL "$URL" -o "$DL/msvc.whl"
mkdir -p "$DL/x" && unzip -q -o "$DL/msvc.whl" -d "$DL/x"
for dll in msvcp140.dll msvcp140_1.dll msvcp140_2.dll vcruntime140_threads.dll concrt140.dll; do
  src="$(find "$DL/x" -iname "$dll" | head -1)"
  if [ -n "$src" ]; then cp "$src" "$OUT/site-packages/torch/lib/"; else echo "     (not in wheel: $dll)"; fi
done
rm -rf "$DL"

echo "4/5  downloading the portable Windows Python ($PBS_FILE)"
if [ ! -f "$OUT/$PBS_FILE" ]; then
  curl -fL "https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${PBS_FILE//+/%2B}" \
    -o "$OUT/$PBS_FILE.part" && mv "$OUT/$PBS_FILE.part" "$OUT/$PBS_FILE"
fi
echo "5/5  copying the models (incl. models/face_swap) into $OUT/models"
python3 -I scripts/download_models.py --check >/dev/null || { echo "ERROR: models/ is incomplete - run scripts/download_models.py first"; exit 1; }
rm -rf "$OUT/models" && mkdir -p "$OUT/models"
for d in models/*/; do d="${d%/}"; cp -c -R "$d" "$OUT/models/" 2>/dev/null || cp -R "$d" "$OUT/models/"; done
rm -rf "$OUT/models/.download_cache"
for pkg in onnxruntime torchvision torch transformers mediapipe; do
  [ -d "$OUT/site-packages/$pkg" ] || { echo "ERROR: $pkg missing from the kit"; exit 1; }
done
ls "$OUT/site-packages/onnxruntime/capi/" | grep -q "onnxruntime.*\.dll\|onnxruntime_pybind11_state.*\.pyd" || { echo "ERROR: onnxruntime is not the Windows build"; exit 1; }
du -sh "$OUT"
echo "Done. Copy $OUT to the USB stick as winkit\\ (see docs/SETUP_WINDOWS.md, Route C)."
