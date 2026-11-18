"""Build the demo evidence for the lab (web/samples/lab/) and the Spot-the-Fake game (web/samples/game/).

    uv run python scripts/build_samples.py --lab
    uv run python scripts/build_samples.py --game

Lab files are picked so the engine gets them right AND they demonstrate different tests.
Game images are ALL re-encoded identically (768 px long side, JPEG q88, metadata stripped) so file
format can't give the answer away; ai_score is the engine's fused score on exactly that file.
"""
from __future__ import annotations

import argparse
import html
import io
import json
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EVAL = ROOT / "eval_data"
LAB = ROOT / "web" / "samples" / "lab"
GAME = ROOT / "web" / "samples" / "game"


def src_meta() -> dict:
    return json.loads((EVAL / "sources.json").read_text())


def engine():
    from server.models import REGISTRY

    if not REGISTRY.loaded:
        REGISTRY.load()
        REGISTRY.warmup()
    from server import pipeline

    return pipeline


def reencode(data: bytes, max_side: int = 768, q: int = 88) -> bytes:
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q, subsampling=2)
    return buf.getvalue()


# --------------------------------------------------------------------------------------- splice demo
def make_splice(base_path: Path, donor_path: Path, out: Path, donor_box=None, at=(0.52, 0.40), size=0.42):
    """A modern 'edited photo': a region of an AI-generated image pasted into a real phone photo (like a generative
    'add object' edit), saved once more as JPEG with the original EXIF kept. The base photo is CROPPED, never
    resized, so its camera noise and JPEG grid stay intact - which is what ELA and the noise map compare against."""
    raw = Image.open(base_path)
    exif = raw.info.get("exif")
    base = ImageOps.exif_transpose(raw).convert("RGB")
    W, H = base.size
    cw, ch = min(W, 2400) // 8 * 8, min(H, 1800) // 8 * 8
    x0, y0 = ((W - cw) // 2) // 8 * 8, ((H - ch) // 2) // 8 * 8
    base = base.crop((x0, y0, x0 + cw, y0 + ch))
    donor = Image.open(donor_path).convert("RGB")
    if donor_box:
        donor = donor.crop(donor_box)
    pw = int(cw * size)
    ph = int(pw * donor.height / donor.width)
    patch = donor.resize((pw, ph), Image.Resampling.LANCZOS)
    yy, xx = np.mgrid[0:ph, 0:pw]
    m = np.maximum(np.abs((xx - pw / 2) / (pw / 2)), np.abs((yy - ph / 2) / (ph / 2)))
    mask = Image.fromarray((np.clip((1.0 - m) * 12, 0, 1) * 255).astype(np.uint8))
    px, py = int(cw * at[0] - pw / 2), int(ch * at[1] - ph / 2)
    base.paste(patch, (px, py), mask)
    base.save(out, "JPEG", quality=92, exif=exif or b"")


SPLICE_BASE = "phone_20220506TRA_EM903_4_Train_interiors_01_jpg.jpg"
SPLICE_DONOR = "diff_stable_diffusion_155_1.jpg"
SPLICE_BOX = None
SPLICE_AT = (0.5, 0.55)
SPLICE_SIZE = 0.38


def build_lab():
    pl = engine()
    meta = src_meta()
    LAB.mkdir(parents=True, exist_ok=True)
    det = json.loads((EVAL / "eval_details.json").read_text()) if (EVAL / "eval_details.json").exists() else {}
    held = det.get("images", {}).get("as_found", {})

    def pick(prefix: str, folder: str, want_fake: bool, prefer_group: str | None = None):
        cands = sorted((EVAL / folder).glob(prefix + "*"))
        good = [c for c in cands if c.name in held and ((held[c.name]["score"] > 70) if want_fake else (held[c.name]["score"] < 20))]
        if prefer_group:
            g2 = [c for c in good if held[c.name]["group"] == prefer_group]
            good = g2 or good
        return (good or cands)[0]

    items = []

    def add(src: Path | None, name: str, kind: str, label: str, title: str, note: str, data: bytes | None = None):
        dst = LAB / name
        if data is not None:
            dst.write_bytes(data)
        else:
            shutil.copyfile(src, dst)
        items.append({"file": name, "kind": kind, "label": label, "title": title, "note": note})
        print("lab:", name)

    phone = pick("phone_", "images/real", False)
    m = meta.get(f"images/real/{phone.name}", {})
    add(phone, "authentic-phone-photo.jpg", "image", "authentic", "Smartphone photo",
        f"Untouched photo straight from a phone camera, EXIF intact. {m.get('licence', '')}, {m.get('author', '')[:60]} "
        f"via Wikimedia Commons.")
    gan = pick("tpdne_", "images/fake", True)
    add(gan, "gan-face.jpg", "image", "synthetic", "GAN face",
        "A person who does not exist - StyleGAN2 face from thispersondoesnotexist.com.")
    diff = EVAL / "images/fake/diff_flux_249_2.webp"   # photorealistic FLUX street scene (held-out, chosen by eye)
    diff = diff if diff.exists() else None
    for c in ([] if diff else sorted((EVAL / "images/fake").glob("diff_*"))):
        if c.name in held and held[c.name]["score"] > 75 and ("flux" in c.name or "mj" in c.name) and held[c.name]["group"] == "diffusion":
            diff = c
            break
    diff = diff or pick("diff_", "images/fake", True)
    gen = meta.get(f"images/fake/{diff.name}", {}).get("generator", "diffusion model")
    add(diff, "diffusion-scene" + diff.suffix, "image", "synthetic", "AI-generated scene",
        f"Text-to-image output ({GENERATOR_NAMES.get(gen, gen).split(' (')[0]}) from the Rapidata public preference dataset (CDLA-Permissive-2.0).")
    # The face-swap sample must be caught by the FACE test itself (not by luck elsewhere): the COCO swap below keeps
    # the GAN face's texture (face score ~99) and shows the classic ghosted eyebrows/lips. It is cropped to the
    # person so the beer bottles on the table (not school-appropriate) are not shown.
    swap_src = EVAL / "images/fake/swap_coco_000000050811__tpdne_01043.jpg"
    buf = io.BytesIO()
    Image.open(swap_src).convert("RGB").crop(SWAP_CROP).save(buf, "JPEG", quality=95)
    add(None, "face-swap.jpg", "image", "synthetic", "Face-swap: AI face pasted into a real photo", SWAP_NOTE,
        data=buf.getvalue())
    # splice demo
    # video
    vr = EVAL / "video/real/nasa_iss_message_crop.mp4"
    if vr.exists():
        add(vr, "real-video.mp4", "video", "authentic", "Real talking video",
            "NASA astronaut message from the International Space Station (public domain, cropped). One of the clips "
            "we used to set the video thresholds: a demonstration, not a test.")
    vf = LAB / "synthetic-video.mp4"
    faces = sorted((EVAL / "images/fake").glob("tpdne_*"))
    subprocess.run([sys.executable, str(ROOT / "scripts/make_synthetic_video.py"), str(faces[-5]), str(vf),
                    "--seconds", "12", "--seed", "11"], check=True)
    items.append({"file": "synthetic-video.mp4", "kind": "video", "label": "synthetic", "title": "AI 'talking photo'",
                  "note": "A StyleGAN face animated with a slow camera move, the way cheap scam videos are made. It never "
                          "blinks. Same recipe as the clips we used to set the video thresholds: a demonstration, not a test."})
    # audio
    # a HELD-OUT speaker (never used to fit the voice probe), not the single narrator of the original set
    from evalcommon import load_items

    a_items = {it["name"]: it for it in load_items("audio")}
    ar = [EVAL / "audio/real" / n for n, it in sorted(a_items.items())
          if it["split"] == "test" and it["y"] == 0 and n.startswith("librispeech_") and it.get("speaker") != "1272"]
    real_a = None
    a_held = det.get("audio", {}).get("as_found", {})
    for c in ar:
        if c.name in a_held and a_held[c.name]["score"] < 30:
            real_a = c
            break
    real_a = real_a or (ar[0] if ar else None)
    if real_a:
        add(real_a, "real-voice" + real_a.suffix, "audio", "authentic", "Real human voice",
            "Read speech from LibriSpeech test-clean (LibriVox public-domain audiobook, CC BY 4.0); this speaker was "
            "never used to tune the voice detector.")
    fake_a = None
    neural = sorted((EVAL / "audio/fake").glob("tts_mms_*")) + sorted((EVAL / "audio/fake").glob("tts_speecht5_*"))
    scored = [c for c in neural if c.name in a_held]
    if scored:  # the most clearly detected modern neural-TTS clip from the held-out set
        fake_a = max(scored, key=lambda c: a_held[c.name]["score"])
    fake_a = fake_a or sorted((EVAL / "audio/fake").glob("tts_speecht5_*"))[0]
    gen = meta.get(f"audio/fake/{fake_a.name}", {}).get("generator", "neural TTS")
    add(fake_a, "synthetic-voice" + fake_a.suffix, "audio", "synthetic", "AI voice",
        f"Text-to-speech generated by our team with {gen}; it imitates no real person.")
    # one honest MISS, so visitors see a fake the engine lets through (outside clip: WaveFake HiFi-GAN, CC BY-SA 4.0,
    # re-rendering a public-domain LJ Speech reading; scored 34 = 'authentic' in the outside-clip test)
    miss = ROOT.parent / "_incoming/media/audio/wavefake_hifigan_LJ001-0001.wav"
    if miss.exists():
        add(miss, "missed-fake-voice.wav", "audio", "synthetic", "A fake VERITAS misses",
            "A public-domain audiobook reading (LJ Speech) re-rendered by a HiFi-GAN neural vocoder (WaveFake dataset, "
            "CC BY-SA 4.0). VERITAS calls it authentic: proof that no detector is perfect.")
    # verify with the engine (the last exhibit is a deliberate miss, so WRONG is expected there)
    for it in items:
        data = (LAB / it["file"]).read_bytes()
        fn = {"image": pl.analyze_image, "video": pl.analyze_video, "audio": pl.analyze_audio}[it["kind"]]
        rep = fn(data, it["file"])
        it["engine_score"] = rep["score"]
        ok = (rep["score"] > 50) == (it["label"] == "synthetic")
        print(f"  {it['file']:28s} label={it['label']:9s} engine={rep['score']:3d} {rep['verdict']:10s} {'OK' if ok else 'WRONG'}")
    (LAB / "manifest.json").write_text(json.dumps(items, indent=1))


SWAP_CROP = (30, 30, 444, 600)
SWAP_NOTE = ("A real photo with a pasted-in face: our team's classic deepfake pipeline (landmarks, triangle warp, "
             "Poisson blend) put a GAN face of a person who does not exist onto it. Look for the ghost eyebrows and lips. "
             "Caught only because the pasted face is itself AI-made: in testing VERITAS caught just 2 of 9 swaps like "
             "this. Photo: COCO / Flickr 8133371246, CC BY-SA 2.0; the edit is ours, same licence.")


# -------------------------------------------------------------------------------------------- game
# generator ids in eval_data/sources.json -> names a visitor recognises (shown on the game's reveal card)
GENERATOR_NAMES = {
    "StyleGAN2 (thispersondoesnotexist.com)": "StyleGAN2 face (thispersondoesnotexist.com)",
    "mj": "Midjourney (text-to-image)", "flux": "FLUX (text-to-image)", "dalle-3": "DALL-E 3 (text-to-image)",
    "stable_diffusion": "Stable Diffusion (text-to-image)",
    "classic landmark face-swap (Delaunay warp + Poisson blend)": "face-swap made by our team (landmark warp + Poisson blend)",
}


def build_game(n_real: int = 15, n_fake: int = 15):
    pl = engine()
    meta = src_meta()
    rnd = random.Random(2111)
    GAME.mkdir(parents=True, exist_ok=True)
    for f in GAME.glob("*.jpg"):
        f.unlink()
    excluded = set(json.loads((ROOT / "scripts" / "game_exclude.json").read_text())) if (ROOT / "scripts" / "game_exclude.json").exists() else set()
    from evalcommon import load_items

    held_out = {it["name"] for it in load_items("images") if it["split"] == "test"}

    seen_prompts: set[str] = set()   # diff_<generator>_<prompt>_<k>: one image per prompt, or a round shows the same scene twice

    def pool(folder, prefix, group=None):
        out = []
        for p in sorted((EVAL / folder).glob(prefix + "*")):
            g = meta.get(f"{folder}/{p.name}", {}).get("group")
            if group is None or g == group:
                out.append(p)
        random.Random(f"{prefix}{group}").shuffle(out)   # stable order: excluding a file only replaces that file
        out = [p for p in out if p.name not in excluded]
        # held-out files first, so the engine's score on the game is not a score on its own calibration files
        out = sorted(out, key=lambda p: p.name not in held_out)
        uniq = []
        for p in out:
            m = re.match(r"diff_.+_(\d+)_\d+\.", p.name)
            if m and m.group(1) in seen_prompts:
                continue
            if m:
                seen_prompts.add(m.group(1))
            uniq.append(p)
        return uniq

    real = pool("images/real", "ffhq_")[:6] + pool("images/real", "coco_", "scene_people")[:4] + \
        pool("images/real", "coco_", "scene")[:2] + pool("images/real", "phone_")[:3]
    fake = pool("images/fake", "tpdne_")[:4] + pool("images/fake", "diff_", "diffusion_people")[:6] + \
        pool("images/fake", "diff_", "diffusion")[:3] + pool("images/fake", "swap_")[:2]
    real, fake = real[:n_real], fake[:n_fake]
    allp = [(p, "real") for p in real] + [(p, "fake") for p in fake]
    rnd.shuffle(allp)
    manifest = []
    for i, (p, lab) in enumerate(allp, 1):
        data = reencode(p.read_bytes())
        name = f"exhibit-{i:02d}.jpg"
        (GAME / name).write_bytes(data)
        rep = pl.analyze_image(data, name)
        m = meta.get(f"images/{lab}/{p.name}", {})
        if lab == "fake":
            g = m.get("generator", "")
            src = GENERATOR_NAMES.get(g, g)
            src = f"AI: {src}" if src else "AI-generated"
            hint = {"gan_face": "Look at the background, earrings and hair edges - GANs smear them.",
                    "diffusion_people": "Check hands, text, and how faces in the background are drawn.",
                    "diffusion": "Look for impossible details: signs, reflections, repeating textures.",
                    "face_swap": "Look at the edge of the face - skin tone and lighting change at the seam."}.get(m.get("group"), "")
        else:
            src = {"face": "Real photo (FFHQ, Flickr)", "scene": "Real photo (COCO, Flickr)",
                   "scene_people": "Real photo (COCO, Flickr)", "phone": "Real smartphone photo (Wikimedia Commons)"}.get(m.get("group"), "Real photo")
            if m.get("author"):
                src += f" - {html.unescape(m['author'])[:50]}, {m.get('licence', '')}"
            hint = "Real camera photos have natural noise, consistent lighting and sensible small details."
        manifest.append({"file": name, "label": lab, "ai_score": int(rep["score"]), "source": src, "hint": hint})
        print(f"game {name} {lab:4s} engine={rep['score']:3d} <- {p.name}")
    (GAME / "manifest.json").write_text(json.dumps(manifest, indent=1))
    # private key (not shipped): which eval file each neutral exhibit name came from
    (EVAL / "game_key.json").write_text(json.dumps({f"exhibit-{i:02d}.jpg": p.name for i, (p, _) in enumerate(allp, 1)}, indent=1))
    acc = np.mean([(m["ai_score"] > 50) == (m["label"] == "fake") for m in manifest])
    print(f"engine accuracy on the game set: {acc * 100:.0f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab", action="store_true")
    ap.add_argument("--game", action="store_true")
    a = ap.parse_args()
    if a.lab:
        build_lab()
    if a.game:
        build_game()
