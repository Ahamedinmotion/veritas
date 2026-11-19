"""Re-create the booth's research demo videos on this computer (run by "1 - SETUP (run once).bat"; needs internet once).

    .venv\\Scripts\\python.exe scripts\\fetch_demo_clips.py                 (Windows; writes demo-clips\\ next to scripts\\)
    .venv/bin/python scripts/fetch_demo_clips.py --out /tmp/clips         (macOS)

Why a download and not a copy: the research datasets (FaceForensics++, Google DFD, Celeb-DF) may not be redistributed,
so these clips are never in the repo, the zip, the website or the Space. This script fetches the same public files from
the same Hugging Face mirrors we used on 18 Nov 2026 (checked by SHA-256), then applies exactly the same trim / crop /
encoding (H.264 High, yuv420p, CRF 18, preset slow, 4 Mbit/s cap, +faststart) with PyAV, so the clips match the ones we tested.

Our own Wav2Lip clip (wav2lip_lipsync_dfd07.mp4) is a derivative we made and is not published anywhere: it is skipped.

Never fails setup: any problem is printed as a note and the script still exits 0 (use --strict for a non-zero exit).
Also copies the public Evidence-locker samples (web/samples/lab) into the folder, for drag-and-drop demos.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import time
import urllib.parse
import urllib.request
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FFPP = ("gonnerthetooner/FaceForensics", "faceforensics_c23/FaceForensics++_C23")
DFDV = "gonnerthetooner/deepfake_video_data"
DFD_O = "google_dfd/DFD_original sequences"
DFD_M = "google_dfd/DFD_manipulated_sequences/DFD_manipulated_sequences"

# file -> source on the Hugging Face mirror, SHA-256 of the raw file (= the mirror's LFS oid, verified 18 Nov 2026),
# first frame, number of frames, crop (w, h, x, y) or None, label, title.
CLIPS = [
    {"file": "ffpp_original_069.mp4", "repo": FFPP[0], "path": f"{FFPP[1]}/original/069.mp4",
     "sha256": "2f160d835fa47ecc2b4db534522792e54e03a878901a1ff6ebb4f7b719a149ba", "start": 0, "frames": 321,
     "crop": None, "label": "REAL", "title": "FaceForensics++ #069 - the original vlogger"},
    {"file": "ffpp_deepfakes_069.mp4", "repo": FFPP[0], "path": f"{FFPP[1]}/Deepfakes/069_961.mp4",
     "sha256": "4fa2d9075035d4c47a6935875824909ad50d4bb9e367c699e36dad3234763183", "start": 0, "frames": 321,
     "crop": None, "label": "FAKE", "title": "FaceForensics++ #069 - Deepfakes face-swap"},
    {"file": "ffpp_face2face_069.mp4", "repo": FFPP[0], "path": f"{FFPP[1]}/Face2Face/069_961.mp4",
     "sha256": "546dc6f62595b3a32f815a1664fc090e4e39be5434efd1766b619b49f3c8ea58", "start": 0, "frames": 321,
     "crop": None, "label": "FAKE", "title": "FaceForensics++ #069 - Face2Face reenactment"},
    {"file": "ffpp_neuraltextures_069.mp4", "repo": FFPP[0], "path": f"{FFPP[1]}/NeuralTextures/069_961.mp4",
     "sha256": "3b7ceec40ef53c98301a73c22029b273a8501af240ceef10f6245e5fbb938287", "start": 0, "frames": 321,
     "crop": None, "label": "FAKE", "title": "FaceForensics++ #069 - NeuralTextures reenactment"},
    # Google DFD: 1280x720 window of the 1080p frame (x=390 / x=340, y=0; no scaling), 24 fps
    {"file": "dfd_original_09.mp4", "repo": DFDV, "path": f"{DFD_O}/09__talking_against_wall.mp4",
     "sha256": "cb3e0db6c169e1eaaee4ffb9dc69c4713e2d478af8bf0870fd8ae2964b1c6250", "start": 240, "frames": 360,
     "crop": (1280, 720, 390, 0), "label": "REAL", "title": "Google DFD actor 09 - original"},
    {"file": "dfd_faceswap_09_13.mp4", "repo": DFDV, "path": f"{DFD_M}/09_13__talking_against_wall__LPT427RY.mp4",
     "sha256": "e6ac341c55f3bff8f13632a881c7fc2bf7886c7baa1b7a74bba09b310e1ad9f0", "start": 240, "frames": 360,
     "crop": (1280, 720, 390, 0), "label": "FAKE", "title": "Google DFD actor 09 with actor 13's face - face-swap"},
    {"file": "dfd_original_07.mp4", "repo": DFDV, "path": f"{DFD_O}/07__talking_against_wall.mp4",
     "sha256": "78d2ede1a6cb70b14c47b39e03a4665436334f8579c5042badc9d6a2fdc3060d", "start": 96, "frames": 270,
     "crop": (1280, 720, 340, 0), "label": "REAL", "title": "Google DFD actor 07 - original (silent)",
     "vbv": False},   # re-cut during the 18 Nov verification without the 4 Mbit/s cap
    # Celeb-DF v2: frames 60-444 (2.0-14.83 s): the first 2 s carry a TV name caption and are cut
    {"file": "celebdf_real_id2_0000.mp4", "repo": DFDV, "path": "celebdf_v2/Celeb-real/id2_0000.mp4",
     "sha256": "d3d715766479b951f631800e226181bad05e833e19f6f921dfa5792be74bcbf4", "start": 60, "frames": 385,
     "crop": None, "label": "REAL", "title": "Celeb-DF id2 - real interview clip"},
    {"file": "celebdf_synthesis_id2_id16_0000.mp4", "repo": DFDV, "path": "celebdf_v2/Celeb-synthesis/id2_id16_0000.mp4",
     "sha256": "5417901032c825b1298bc6c429beea40f1c602750a6a0599eb69b16df177a404", "start": 60, "frames": 385,
     "crop": None, "label": "FAKE", "title": "Celeb-DF id2 with id16's face - high-quality face-swap"},
]
SKIPPED_NOTE = ("wav2lip_lipsync_dfd07.mp4 (our own Wav2Lip lip-sync clip) is not downloaded: it is a derivative we "
                "made and do not publish. If you need it, copy it from the team's USB stick into this folder.")

README = """VERITAS demo clips
==================

Drag any of these files into the VERITAS lab (Analyze tab).

The .mp4 files in this folder are research clips from FaceForensics++, the Google DeepFake Detection
dataset and Celeb-DF. They were downloaded during setup from public Hugging Face mirrors and are for
showing at the booth ONLY: never post them online, never hand them out or copy them for visitors.
They are demonstrations, not a fair test: the three FF++ #069 fakes are in the training data of one of
the face-swap networks (GenD), and we chose the face-swap detector pair after seeing its results on
Celeb-DF and Google DFD clips. Expect the DFD actor-09 face-swap to read only "suspicious".

The Celeb-DF clips show real celebrities, and the fake one is a deepfake of a real celebrity: our ethics
rules keep them out of the live demo. Use them only if a judge asks.

{rows}

{skipped}

The "Evidence locker samples" folder holds the same public samples as the lab's Evidence locker
(photos, voices and videos with their own licences: see the notes in the lab).
"""


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def download(repo: str, path: str, want: str, dst: Path) -> None:
    """Public, ungated Hugging Face dataset file -> dst (no login, no token). Checked by SHA-256."""
    if dst.exists() and sha256(dst) == want:
        return
    url = f"https://huggingface.co/datasets/{repo}/resolve/main/{urllib.parse.quote(path)}"
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "veritas-setup/1.0"})
            tmp = dst.with_suffix(".part")
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            got = sha256(tmp)
            if got != want:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"the mirror file changed (SHA-256 {got[:12]}..., expected {want[:12]}...)")
            tmp.replace(dst)
            return
        except Exception as e:  # noqa: BLE001
            last = e
            if "401" in str(e) or "403" in str(e):
                raise RuntimeError(f"{e} - the mirror now needs a Hugging Face login") from e
            time.sleep(2 + 3 * attempt)
    raise RuntimeError(f"download failed: {last}")


def pick_encoder():
    import av

    for name in ("libx264", "libopenh264", "h264_mf", "mpeg4"):
        try:
            av.codec.Codec(name, "w")
            return name
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("no video encoder available in PyAV")


def transcode(src: Path, dst: Path, start: int, frames: int, crop, vbv: bool = True) -> int:
    """Frames [start, start+frames) of src, optional crop, -> H.264 High yuv420p CRF 18 preset slow +faststart.
    Same filters as the ffmpeg command used on 18 Nov (crop, then format=yuv420p). Returns frames written."""
    import av

    enc = pick_encoder()
    tmp = dst.with_name(dst.stem + ".tmp.mp4")
    with av.open(str(src)) as inp:
        ist = inp.streams.video[0]
        fps = ist.average_rate or ist.guessed_rate or Fraction(30)
        w, h = (crop[0], crop[1]) if crop else (ist.codec_context.width, ist.codec_context.height)
        graph = av.filter.Graph()
        chain = [graph.add_buffer(template=ist)]
        if crop:
            chain.append(graph.add("crop", f"{crop[0]}:{crop[1]}:{crop[2]}:{crop[3]}"))
        chain.append(graph.add("format", "yuv420p"))
        chain.append(graph.add("buffersink"))
        for a, b in zip(chain, chain[1:]):
            a.link_to(b)
        graph.configure()

        with av.open(str(tmp), "w", format="mp4", options={"movflags": "+faststart"}) as out:
            ost = out.add_stream(enc, rate=fps)
            ost.width, ost.height, ost.pix_fmt = w, h, "yuv420p"
            if enc == "libx264":   # = ffmpeg -c:v libx264 -preset slow -crf 18 -maxrate 4M -bufsize 8M (frame threads)
                ost.options = {"crf": "18", "preset": "slow", "profile": "high"}
                if vbv:
                    ost.options = {**ost.options, "maxrate": "4000k", "bufsize": "8000k"}
                ost.codec_context.thread_type = "FRAME"
                ost.codec_context.thread_count = 15   # the originals' x264 threads=15: same output on any CPU count
            else:
                ost.bit_rate = 4_000_000
            tb = Fraction(1, 1) / fps          # frame pts = frame number (the stream's own time base may differ)
            ost.codec_context.time_base = tb
            n = 0
            for i, frame in enumerate(inp.decode(ist)):
                if i < start:
                    continue
                if n >= frames:
                    break
                graph.push(frame)
                while True:
                    try:
                        f2 = graph.pull()
                    except (av.error.BlockingIOError, av.error.EOFError):
                        break
                    f2.pts, f2.time_base = n, tb
                    f2.pict_type = av.video.frame.PictureType.NONE
                    for pkt in ost.encode(f2):
                        out.mux(pkt)
                    n += 1
            for pkt in ost.encode(None):
                out.mux(pkt)
    if n != frames:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"the source had only {n} usable frames (expected {frames})")
    tmp.replace(dst)
    return n


def copy_locker(out: Path) -> int:
    src = ROOT / "web" / "samples" / "lab"
    dst = out / "Evidence locker samples"
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(src.glob("*")):
        if p.is_file() and p.suffix.lower() != ".json":
            shutil.copyfile(p, dst / p.name)
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(ROOT / "demo-clips"), help="output folder (default: demo-clips next to scripts)")
    ap.add_argument("--raw-dir", default=None, help="use raw dataset files from this folder (same mirror paths) "
                                                    "instead of downloading them")
    ap.add_argument("--only", nargs="*", default=None, help="only these output file names")
    ap.add_argument("--force", action="store_true", help="re-create clips that already exist")
    ap.add_argument("--keep-raw", action="store_true", help="keep the downloaded raw files")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any clip failed")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cache = out / ".download"
    clips = [c for c in CLIPS if not a.only or c["file"] in a.only]
    print(f"VERITAS demo clips -> {out}")
    ok, failed, t0 = [], [], time.perf_counter()
    for c in clips:
        dst = out / c["file"]
        if dst.exists() and dst.stat().st_size > 0 and not a.force:
            print(f"  ok    {c['file']} (already there)")
            ok.append(c)
            continue
        try:
            if a.raw_dir:
                raw = Path(a.raw_dir) / c["path"]
                if not raw.exists() or sha256(raw) != c["sha256"]:
                    raise RuntimeError(f"{raw} is missing or not the verified file")
            else:
                cache.mkdir(parents=True, exist_ok=True)
                raw = cache / (c["path"].replace("/", "__").replace(" ", "_"))
                print(f"  ...   {c['file']}: downloading from huggingface.co/datasets/{c['repo']}", flush=True)
                download(c["repo"], c["path"], c["sha256"], raw)
            t = time.perf_counter()
            n = transcode(raw, dst, c["start"], c["frames"], c["crop"], c.get("vbv", True))
            print(f"  ok    {c['file']} ({n} frames, {dst.stat().st_size / 1e6:.1f} MB, {time.perf_counter() - t:.0f} s)",
                  flush=True)
            ok.append(c)
        except Exception as e:  # noqa: BLE001
            print(f"  NOTE  {c['file']} skipped: {e}", flush=True)
            failed.append(c)
    if not a.keep_raw:
        shutil.rmtree(cache, ignore_errors=True)
    print(f"  NOTE  {SKIPPED_NOTE}")
    try:
        n = copy_locker(out)
        print(f"  ok    {n} Evidence-locker samples copied")
    except Exception as e:  # noqa: BLE001
        print(f"  NOTE  could not copy the Evidence-locker samples: {e}")
    rows = "\n".join(f"  {c['label']:4s}  {c['file']:38s} {c['title']}" for c in CLIPS if (out / c["file"]).exists())
    try:
        (out / "README.txt").write_text(README.format(rows=rows or "  (no research clips could be downloaded)",
                                                      skipped=SKIPPED_NOTE), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"  NOTE  could not write README.txt: {e}")
    print(f"  Demo clips: {len(ok)} of {len(clips)} research clips ready in {time.perf_counter() - t0:.0f} s"
          + ("" if not failed else f" - {len(failed)} skipped (the lab works without them)"))
    return 1 if (a.strict and failed) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001  never break setup
        print(f"  NOTE  demo clips skipped: {e}")
        sys.exit(0)
