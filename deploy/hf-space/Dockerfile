# VERITAS online engine - Hugging Face Docker Space (free cpu-basic: 2 vCPU, 16 GB RAM).
# Assembled and uploaded by scripts/build_hf_space.py (this file ends up at the Space root). It serves the whole site
# (story + lab + API) from one origin on port 7860. Models are downloaded at BUILD time; at run time nothing is
# fetched from the internet (HF_HUB_OFFLINE=1). Uploads are analysed in memory and never stored (server/online.py).
FROM python:3.12-slim

# OpenCV (pulled in by MediaPipe) needs libGL + glib; MediaPipe's Tasks runtime may look for EGL/GLES.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libegl1 libgles2 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /uvx /usr/local/bin/

# Hugging Face runs the container as user 1000 - build as that user so caches (numba, matplotlib) stay writable.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/app/.venv/bin:$PATH \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3.12 \
    PYTHONUNBUFFERED=1
WORKDIR /home/user/app

# 1) Python environment exactly as locked (the lock pins the Linux CPU build of torch).
COPY --chown=user pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project && rm -rf /home/user/.cache/uv

# 2) Models (about 2.5 GB), downloaded once at build time. The face-swap ONNX files come from the VERITAS model
#    mirror on Hugging Face (SHA-256 checked); everything else from the original publishers.
COPY --chown=user scripts/download_models.py scripts/export_faceswap_onnx.py scripts/faceswap_onnx_reference.json scripts/
COPY --chown=user web/vendor/mediapipe/face_landmarker.task web/vendor/mediapipe/face_landmarker.task
RUN python scripts/download_models.py \
 && test -s models/face_swap/gend_clip_int8.onnx \
 && rm -rf models/.download_cache /home/user/.cache/huggingface

# 3) The app itself (engine + web site).
COPY --chown=user . .

# Online settings (see deploy/hf-space/README.md "Engine settings"). cpu-basic has 2 vCPUs, but os.cpu_count() in a
# container reports the host's CPUs, so pin the thread counts. Face-swap mode int8: on 2 CPU cores a 10 s video took
# 15-18 s with int8 vs 29-40 s with fp32 (Linux container capped at 2 Apple-silicon cores, 19 Nov 2026); cpu-basic is
# slower still, and fp32 would likely miss the ~90 s target. All Evidence-locker exhibits keep their scores in int8.
# To use the fp32 pair instead: change VERITAS_FACESWAP below (or set a Space variable VERITAS_FACESWAP=fp32).
ENV VERITAS_ONLINE=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    VERITAS_PORT=7860 \
    VERITAS_THREADS=2 \
    OMP_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    VERITAS_FACESWAP=int8 \
    VERITAS_VIDEO_FRAMES=32

# Self-test on the real Evidence-locker exhibits: proves the engine works on Linux and pre-compiles the numba / font /
# bytecode caches so the first visitor does not wait. Differences are logged loudly but do not fail the build.
RUN python scripts/selftest.py || echo "!!!!! VERITAS SELFTEST REPORTED DIFFERENCES - read the lines above !!!!!"

EXPOSE 7860
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860", "--timeout-keep-alive", "75", "--no-access-log"]
