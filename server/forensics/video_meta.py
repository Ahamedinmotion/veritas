"""Container metadata for videos (MP4/MOV/WebM tags) - the video equivalent of EXIF."""
from __future__ import annotations

import re

from .base import calibrated, make_test
from .metadata import AI_PATTERNS

NAME = "Metadata & Provenance"
EXPLAIN = ("Video files carry container tags: phones record make, model and creation time, editors and "
           "converters stamp their encoder name, and some AI video tools add their own name or a C2PA "
           "content credential. Tags are easy to strip, so they are supporting evidence only.")


def run(tags: dict, raw: bytes, codec: str) -> tuple[dict, dict]:
    low = " ".join(f"{k}={v}" for k, v in tags.items()).lower()
    head = raw[:2_000_000] + raw[-2_000_000:]
    c2pa = (b"jumb" in head and b"c2pa" in head) or b"urn:c2pa" in head
    ai = [label for pat, label in AI_PATTERNS if re.search(pat, low)]
    if c2pa and b"trainedalgorithmicmedia" in head.lower():
        ai.append("C2PA: trained algorithmic media")
    camera = [v for k, v in tags.items() if any(s in k.lower() for s in ("make", "model", "com.apple.quicktime", "com.android"))]
    encoder = tags.get("encoder") or tags.get("video.encoder") or ""
    creation = tags.get("creation_time", "")
    flags = []
    if camera:
        flags.append("Device tags: " + ", ".join(sorted(set(camera)))[:80])
    if creation:
        flags.append(f"Created {creation[:19]}")
    if encoder:
        flags.append(f"Encoder: {encoder[:40]}")
    for a in ai:
        flags.append(f"AI marker: {a}")
    if c2pa:
        flags.append("C2PA content credentials present")
    if not tags:
        flags.append("No container metadata")
    if ai:
        s, finding = 97, f"AI-tool marker in the file's metadata: {ai[0][:40]}."
    elif camera:
        s, finding = 10, "Phone/camera device tags present in the container."
    elif "lavf" in encoder.lower() or "lavc" in encoder.lower():
        s, finding = 40, "Re-encoded with FFmpeg; original device tags are gone."
    elif creation:
        s, finding = 32, "Creation time present but no device information."
    else:
        s, finding = 45, "No useful metadata; stripped by an app or never from a camera."
    test = make_test("metadata", NAME, "metadata", score=calibrated("metadata_video", s), finding=finding,
                     explain=EXPLAIN, metrics={"tags": len(tags), "codec": codec, "ai_markers": len(ai), "raw": s})
    exif = {k: v for k, v in tags.items() if not k.startswith("video.handler") and len(k) < 40}
    return test, {"exif": dict(list(exif.items())[:16]), "flags": flags, "ai_marker": bool(ai)}
