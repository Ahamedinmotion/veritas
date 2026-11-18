"""Build the VERITAS evaluation set (eval_data/, gitignored) from small public, openly licensed sources.

Run ONCE on a machine with internet (development Mac), from veritas/:
    uv run --with pyarrow python scripts/build_eval_data.py [--part images|audio|video|all]

Every file written is logged with its source + licence in eval_data/sources.json
(docs/DATA_SOURCES.md is the human-readable version). The script is idempotent: files that
already exist are skipped, so it can be re-run after a network hiccup.

Nothing here is needed at the fair - the booth laptop never touches eval_data/.
"""
from __future__ import annotations

import argparse
import io
import json
import random
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval_data"
UA = {"User-Agent": "science-fair-eval-script/1.0 (educational, non-commercial)"}
RNG = random.Random(2026)

SOURCES: dict[str, dict] = {}
SRC_FILE = OUT / "sources.json"
if SRC_FILE.exists():
    SOURCES = json.loads(SRC_FILE.read_text())


def save_sources():
    SRC_FILE.parent.mkdir(parents=True, exist_ok=True)
    SRC_FILE.write_text(json.dumps(SOURCES, indent=1, sort_keys=True))


def record(path: Path, **meta):
    SOURCES[str(path.relative_to(OUT))] = meta


def curl_get(url: str) -> bytes:
    """upload.wikimedia.org rate-limits Python's urllib aggressively; curl (HTTP/2) is accepted."""
    r = subprocess.run(["curl", "-sSfL", "--retry", "3", "--retry-delay", "5", "-A", UA["User-Agent"], url],
                       capture_output=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"curl failed {url}: {r.stderr[:200]!r}")
    return r.stdout


def http_get(url: str, tries: int = 4, pause: float = 2.0) -> bytes:
    if "upload.wikimedia.org" in url:
        return curl_get(url)
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(pause * (i + 1) * (5 if "429" in str(e) else 1))
    raise RuntimeError(f"GET failed {url}: {last}")


def hf_file(repo: str, filename: str, repo_type: str = "dataset") -> Path:
    from huggingface_hub import hf_hub_download

    return Path(hf_hub_download(repo, filename, repo_type=repo_type))


# ----------------------------------------------------------------------------------------- images
def images_ffhq(n=36):
    """Real faces: FFHQ (Flickr-Faces-HQ), 1024x1024 PNG."""
    d = OUT / "images/real"
    d.mkdir(parents=True, exist_ok=True)
    idx = RNG.sample(range(0, 10000), n)
    for i in idx:
        out = d / f"ffhq_{i:05d}.png"
        if out.exists():
            continue
        p = hf_file("marcosv/ffhq-dataset", f"Part1/{i:05d}.png")
        out.write_bytes(p.read_bytes())
        record(out, label="real", group="face", source="FFHQ via huggingface.co/datasets/marcosv/ffhq-dataset",
               licence="Images: Flickr CC BY / CC BY-NC / PD (per image); dataset: CC BY-NC-SA 4.0 (NVIDIA)")
    print("ffhq done")


def images_coco(n_person=16, n_other=16):
    """Real scenes: COCO val2017 (Flickr photos)."""
    d = OUT / "images/real"
    d.mkdir(parents=True, exist_ok=True)
    ann = json.loads(hf_file("LibreYOLO/coco-val2017-mini500", "annotations/instances_val2017_mini500.json").read_text())
    person_imgs = {a["image_id"] for a in ann["annotations"] if a["category_id"] == 1 and a["area"] > 8000}
    imgs = sorted(ann["images"], key=lambda x: x["id"])
    RNG.shuffle(imgs)
    pick = [im for im in imgs if im["id"] in person_imgs][:n_person] + [im for im in imgs if im["id"] not in person_imgs][:n_other]
    for im in pick:
        out = d / f"coco_{im['id']:012d}.jpg"
        if out.exists():
            continue
        p = hf_file("LibreYOLO/coco-val2017-mini500", f"images/val2017/{im['file_name']}")
        out.write_bytes(p.read_bytes())
        record(out, label="real", group="scene_people" if im["id"] in person_imgs else "scene",
               source="COCO val2017 via huggingface.co/datasets/LibreYOLO/coco-val2017-mini500",
               licence="Flickr CC licences per image (COCO terms: CC BY 4.0 annotations)")
    print("coco done")


COMMONS_CATS = [
    "Category:Taken with Samsung Galaxy S21 5G",
    "Category:Taken with Samsung Galaxy S23",
    "Category:Taken with Google Pixel 6",
    "Category:Taken with Google Pixel 4a",
    "Category:Taken with Xiaomi 12 (main camera)",
    "Category:Taken with OnePlus 7T",
    "Category:Taken with Xiaomi 14T Pro",
]


def commons_api(params):
    params = dict(params, format="json")
    u = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    return json.loads(http_get(u, pause=3))


def images_commons_phone(per_cat=3):
    """Real smartphone photos WITH camera EXIF from Wikimedia Commons (free licences)."""
    d = OUT / "images/real"
    d.mkdir(parents=True, exist_ok=True)
    ok_lic = ("CC BY", "CC0", "Public domain", "CC BY-SA")
    for cat in COMMONS_CATS:
        have = [k for k, v in SOURCES.items() if v.get("commons_cat") == cat]
        if len(have) >= per_cat:
            continue
        r = commons_api(dict(action="query", generator="categorymembers", gcmtitle=cat, gcmtype="file", gcmlimit=60,
                             prop="imageinfo", iiprop="url|size|mime|extmetadata"))
        pages = list(r.get("query", {}).get("pages", {}).values())
        RNG.shuffle(pages)
        got = len(have)
        for pg in pages:
            if got >= per_cat:
                break
            ii = pg["imageinfo"][0]
            lic = ii.get("extmetadata", {}).get("LicenseShortName", {}).get("value", "")
            if ii.get("mime") != "image/jpeg" or not lic.startswith(ok_lic) or ii["size"] > 9_000_000:
                continue
            safe = "".join(c if c.isalnum() else "_" for c in pg["title"][5:60])
            out = d / f"phone_{safe}.jpg"
            if out.exists():
                got += 1
                continue
            time.sleep(6)
            try:
                out.write_bytes(http_get(ii["url"], pause=4))
            except Exception as e:  # noqa: BLE001
                print("  skip", e)
                continue
            artist = ii.get("extmetadata", {}).get("Artist", {}).get("value", "")
            record(out, label="real", group="phone", source=ii["descriptionurl"], licence=lic,
                   author=_strip_html(artist)[:120], commons_cat=cat)
            got += 1
            save_sources()
        print("  commons", cat, got)
        time.sleep(2)
    print("commons done")


def _strip_html(s: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", s).strip()


def images_tpdne(n=36):
    """GAN faces: StyleGAN2 faces from thispersondoesnotexist.com (dataset: javi22, MIT)."""
    d = OUT / "images/fake"
    d.mkdir(parents=True, exist_ok=True)
    idx = RNG.sample(range(1, 9980), n)
    for i in idx:
        out = d / f"tpdne_{i:05d}.jpg"
        if out.exists():
            continue
        p = hf_file("javi22/this-person-does-not-exist-10k", f"face ({i}).jpg")
        out.write_bytes(p.read_bytes())
        record(out, label="fake", group="gan_face", generator="StyleGAN2 (thispersondoesnotexist.com)",
               source="huggingface.co/datasets/javi22/this-person-does-not-exist-10k", licence="MIT (dataset card)")
    print("tpdne done")


PEOPLE_WORDS = ("man", "woman", "person", "people", "boy", "girl", "child", "player", "men", "women", "lady", "guy", "kid")


def images_rapidata(per_model=11):
    """Modern diffusion images (DALL-E 3, FLUX.1, Midjourney, Stable Diffusion) from Rapidata's
    human-preference dataset (CDLA-Permissive-2.0). Prompts are COCO-style photo captions."""
    import pyarrow.parquet as pq

    d = OUT / "images/fake"
    d.mkdir(parents=True, exist_ok=True)
    want: dict[str, list] = {}
    shard_ids = [1, 5, 9, 13, 17, 21, 25]
    for sid in shard_ids:
        if want and all(len(v) >= per_model for v in want.values()) and len(want) >= 4:
            break
        fn = f"data/train_{sid:04d}-00000-of-00001.parquet"
        try:
            p = hf_file("Rapidata/700k_Human_Preference_Dataset_FLUX_SD3_MJ_DALLE3", fn)
        except Exception as e:  # noqa: BLE001
            print("  rapidata shard fail", fn, e)
            continue
        t = pq.read_table(p, columns=["prompt", "image1", "image2", "model1", "model2", "image1_path", "image2_path"])
        rows = t.to_pylist()
        RNG.shuffle(rows)
        for r in rows:
            for k in ("1", "2"):
                model = r["model" + k]
                lst = want.setdefault(model, [])
                if len(lst) >= per_model:
                    continue
                path = r["image" + k + "_path"]
                if any(x[1] == path for x in lst):
                    continue
                has_people = any(f" {w} " in f" {r['prompt'].lower()} " for w in PEOPLE_WORDS)
                # aim for ~half people
                n_people = sum(1 for x in lst if x[2])
                if has_people and n_people >= (per_model + 1) // 2:
                    continue
                if not has_people and (len(lst) - n_people) >= per_model // 2:
                    continue
                lst.append((r["image" + k]["bytes"], path, has_people, r["prompt"]))
        print("  rapidata", sid, {m: len(v) for m, v in want.items()})
    for model, lst in want.items():
        for b, path, has_people, prompt in lst:
            safe = path.replace("/", "_").replace(".jpg", "")
            ext = ".png" if b[:4] == b"\x89PNG" else (".webp" if b[8:12] == b"WEBP" else ".jpg")
            out = d / f"diff_{safe}{ext}"
            if not out.exists():
                out.write_bytes(b)
            record(out, label="fake", group="diffusion_people" if has_people else "diffusion",
                   generator=model, prompt=prompt[:160],
                   source="huggingface.co/datasets/Rapidata/700k_Human_Preference_Dataset_FLUX_SD3_MJ_DALLE3",
                   licence="CDLA-Permissive-2.0")
    print("rapidata done")


# ------------------------------------------------------------------------------------------ audio
def audio_librispeech(n=24):
    """Real read speech: LibriSpeech (LibriVox public-domain audiobooks), CC BY 4.0."""
    import pyarrow.parquet as pq
    import soundfile as sf

    d = OUT / "audio/real"
    d.mkdir(parents=True, exist_ok=True)
    p = hf_file("hf-internal-testing/librispeech_asr_dummy", "clean/validation-00000-of-00001.parquet")
    rows = pq.read_table(p).to_pylist()
    seen_spk = {}
    for r in rows:
        spk = r["speaker_id"]
        if seen_spk.get(spk, 0) >= 12:
            continue
        a = r["audio"]
        data, sr = sf.read(io.BytesIO(a["bytes"]))
        if len(data) / sr < 4:
            continue
        seen_spk[spk] = seen_spk.get(spk, 0) + 1
        out = d / f"librispeech_{r['id']}.flac"
        if not out.exists():
            out.write_bytes(a["bytes"])
        record(out, label="real", group="read_speech", source="LibriSpeech dev-clean (hf-internal-testing/librispeech_asr_dummy)",
               licence="CC BY 4.0", speaker=str(spk))
        if sum(seen_spk.values()) >= n:
            break
    print("librispeech done", sum(seen_spk.values()))


def audio_asvspoof(n_real=20, n_fake=24):
    """ASVspoof 2019 LA evaluation set: bona-fide VCTK speech + 13 TTS/voice-conversion attacks (ODC-BY)."""
    import pyarrow.parquet as pq

    d_r, d_f = OUT / "audio/real", OUT / "audio/fake"
    d_r.mkdir(parents=True, exist_ok=True)
    d_f.mkdir(parents=True, exist_ok=True)
    repo = "SpeechAntiSpoofingBenchmarks/ASVspoof2019_LA"
    p = hf_file(repo, "data/test-00000-of-00009.parquet")
    pf = pq.ParquetFile(p)
    print("  asvspoof schema", pf.schema_arrow.names)
    t = pq.read_table(p)
    rows = t.to_pylist()
    RNG.shuffle(rows)
    proto = hf_file(repo, "protocols/ASVspoof2019.LA.cm.eval.trl.txt").read_text().split("\n")
    attack = {}
    for line in proto:
        parts = line.split()
        if len(parts) >= 5:
            attack[parts[1]] = parts[3]          # utterance id -> attack id ('-' for bona fide)
    got_r, got_f, per_atk = 0, 0, {}
    for r in rows:
        uid = r["path"].rsplit(".", 1)[0]
        is_real = int(r["label"]) == 0          # 0 = bona fide, 1 = spoof in this parquet export
        atk = attack.get(uid, "?")
        b = r["audio"]["bytes"] if isinstance(r["audio"], dict) else r["audio"]
        if is_real and got_r < n_real:
            out = d_r / f"asvspoof_{uid}.flac"
            got_r += 1
            meta = dict(label="real", group="vctk_bonafide")
        elif not is_real and got_f < n_fake and per_atk.get(atk, 0) < 2:
            out = d_f / f"asvspoof_{uid}_{atk}.flac"
            per_atk[atk] = per_atk.get(atk, 0) + 1
            got_f += 1
            meta = dict(label="fake", group="asvspoof_tts_vc", generator=f"ASVspoof2019 attack {atk}")
        else:
            continue
        if not out.exists():
            out.write_bytes(b)
        record(out, source=f"huggingface.co/datasets/{repo}", licence="ODC-BY (ASVspoof 2019)", **meta)
        if got_r >= n_real and got_f >= n_fake:
            break
    print("asvspoof done", got_r, got_f, per_atk)


def audio_librispeech_multi(n_speakers=24, max_s=14.0):
    """More real read speech: ONE utterance from each of 24 different LibriSpeech test-clean speakers, so the voice
    probe cannot learn 'this one narrator = real' (CC BY 4.0, openslr/librispeech_asr, ~350 MB parquet)."""
    import pyarrow.parquet as pq
    import soundfile as sf

    d = OUT / "audio/real"
    d.mkdir(parents=True, exist_ok=True)
    pf = pq.ParquetFile(hf_file("openslr/librispeech_asr", "clean/test/0000.parquet"))
    seen = set()
    for batch in pf.iter_batches(batch_size=64, columns=["audio", "speaker_id", "id"]):
        for r in batch.to_pylist():
            spk = r["speaker_id"]
            if spk in seen:
                continue
            data, sr = sf.read(io.BytesIO(r["audio"]["bytes"]))
            if len(data) / sr < 5:
                continue
            seen.add(spk)
            out = d / f"librispeech_{r['id']}.flac"
            if not out.exists():
                sf.write(out, data[: int(max_s * sr)], sr, format="FLAC")
            record(out, label="real", group="read_speech", source="LibriSpeech test-clean (openslr/librispeech_asr)",
                   licence="CC BY 4.0", speaker=str(spk))
            if len(seen) >= n_speakers:
                print("librispeech multi-speaker done", len(seen))
                return


def audio_fleurs(n=24, max_s=14.0):
    """Everyday real speech: FLEURS en_us dev (CC BY 4.0) - volunteers reading Wikipedia sentences on their own
    microphones, so recording conditions vary far more than in studio corpora. One clip per sentence."""
    import tarfile

    import soundfile as sf

    d = OUT / "audio/real"
    d.mkdir(parents=True, exist_ok=True)
    tsv = hf_file("google/fleurs", "data/en_us/dev.tsv").read_text().splitlines()
    rows = [ln.split("\t") for ln in tsv if ln.strip()]
    wanted, seen_sent = {}, set()
    for r in rows:
        sid, fname = r[0], r[1]
        if sid in seen_sent:
            continue
        seen_sent.add(sid)
        wanted[fname] = sid
    tf = tarfile.open(hf_file("google/fleurs", "data/en_us/audio/dev.tar.gz"), "r:gz")
    got = 0
    for m in tf:
        base = m.name.rsplit("/", 1)[-1]
        if not m.isfile() or base not in wanted:
            continue
        data, sr = sf.read(io.BytesIO(tf.extractfile(m).read()))
        if len(data) / sr < 5:
            continue
        out = d / f"fleurs_en_{base.rsplit('.', 1)[0]}.flac"
        if not out.exists():
            sf.write(out, data[: int(max_s * sr)], sr, format="FLAC")
        record(out, label="real", group="everyday_speech", source="FLEURS en_us dev (google/fleurs)",
               licence="CC BY 4.0", speaker=f"fleurs_{wanted[base]}")
        got += 1
        if got >= n:
            break
    print("fleurs done", got)


def audio_vocoded():
    """Matched pairs, WaveFake-style: each LibriSpeech test-clean utterance is re-rendered by a neural vocoder
    (SpeechT5's HiFi-GAN, MIT) from its own mel spectrogram. Same speaker, same words, same room - only the
    vocoder differs, so the voice probe must learn vocoder artefacts instead of 'audiobook speech = real'.
    Evaluation only; never shipped or played at the booth."""
    import numpy as np
    import soundfile as sf
    import torch
    from transformers import SpeechT5FeatureExtractor, SpeechT5HifiGan

    fe = SpeechT5FeatureExtractor.from_pretrained("microsoft/speecht5_tts")
    voc = SpeechT5HifiGan.from_pretrained("microsoft/speecht5_hifigan").eval()
    d = OUT / "audio/fake"
    n = 0
    for k, v in sorted(SOURCES.items()):
        if not (k.startswith("audio/real/librispeech_") and "test-clean" in v.get("source", "")):
            continue
        src = OUT / k
        out = d / ("vocoded_" + src.stem + ".wav")
        if not out.exists():
            w, sr = sf.read(src)
            mel = fe(audio_target=w, sampling_rate=16000, return_tensors="pt")["input_values"][0]
            with torch.no_grad():
                y = voc(mel).numpy()
            sf.write(out, y / max(1e-6, float(np.abs(y).max())) * 0.9, 16000)
        record(out, label="fake", group="vocoded_speech", generator="HiFi-GAN vocoder resynthesis (SpeechT5)",
               source=f"made by scripts/build_eval_data.py from {src.name}", licence="derived from LibriSpeech (CC BY 4.0)",
               speaker=v.get("speaker"))
        n += 1
    print("vocoded pairs", n)


def audio_asvspoof_speakers():
    """Add the ASVspoof speaker id (from the official protocol) to every ASVspoof clip, so the calibration /
    held-out split can keep each speaker on one side."""
    proto = hf_file("SpeechAntiSpoofingBenchmarks/ASVspoof2019_LA", "protocols/ASVspoof2019.LA.cm.eval.trl.txt")
    spk = {}
    for line in proto.read_text().split("\n"):
        parts = line.split()
        if len(parts) >= 5:
            spk[parts[1]] = parts[0]
    n = 0
    for k, v in SOURCES.items():
        if "/asvspoof_" in k:
            uid = "_".join(k.rsplit("/", 1)[-1].split(".")[0].split("_")[1:4])   # LA_E_1234567
            if uid in spk:
                v["speaker"] = spk[uid]
                n += 1
    print("asvspoof speakers tagged", n)


def audio_unidata():
    """Real voices + their AI voice-clones (CC BY-NC-ND 4.0, sample of a commercial dataset)."""
    from huggingface_hub import HfApi

    repo = "UniDataPro/real-vs-fake-human-voice-deepfake-audio"
    files = [s.rfilename for s in HfApi().dataset_info(repo).siblings]
    for f in files:
        if not f.endswith((".mp3", ".m4a", ".wav")):
            continue
        is_real = "original" in f
        sub = "real" if is_real else "fake"
        d = OUT / "audio" / sub
        d.mkdir(parents=True, exist_ok=True)
        # keep at most 2 clones per speaker to balance
        if not is_real and not any(f.endswith(f"synthetic_{k}.mp3") for k in (1, 2)):
            continue
        out = d / ("unidata_" + f.replace("/", "_"))
        if not out.exists():
            out.write_bytes(hf_file(repo, f).read_bytes())
        record(out, label=sub, group="voice_clone" if not is_real else "original_voice",
               source=f"huggingface.co/datasets/{repo}", licence="CC BY-NC-ND 4.0 (evaluation only, not redistributed)")
    print("unidata done")


TTS_LINES = [
    "Science is not only a disciple of reason but also one of romance and passion.",
    "The quick brown fox jumps over the lazy dog near the river bank.",
    "Please remember to submit your science project before Friday afternoon.",
    "Every image tells a story, but not every story is true.",
    "Our school exhibition opens at nine in the morning on Saturday.",
    "Artificial intelligence can now copy a voice from just a few seconds of audio.",
    "The weather in Thiruvananthapuram is warm and humid this week.",
    "Light travels at nearly three hundred thousand kilometres every second.",
    "Can you tell whether this voice belongs to a real human being?",
    "Water boils at one hundred degrees Celsius at sea level.",
]


def audio_local_tts():
    """Modern neural TTS generated locally: Meta MMS-TTS (VITS, CC BY-NC 4.0), Microsoft SpeechT5 + HiFi-GAN (MIT),
    and a couple of macOS `say` clips. Text is generic, no real person is imitated."""
    import numpy as np
    import soundfile as sf
    import torch

    d = OUT / "audio/fake"
    d.mkdir(parents=True, exist_ok=True)
    # MMS-TTS (VITS)
    try:
        from transformers import AutoTokenizer, VitsModel

        tok = AutoTokenizer.from_pretrained("facebook/mms-tts-eng")
        m = VitsModel.from_pretrained("facebook/mms-tts-eng").eval()
        for i, line in enumerate(TTS_LINES[:8]):
            out = d / f"tts_mms_vits_{i:02d}.wav"
            if not out.exists():
                torch.manual_seed(i)
                with torch.no_grad():
                    w = m(**tok(line, return_tensors="pt")).waveform[0].numpy()
                sf.write(out, w / max(1e-6, np.abs(w).max()) * 0.9, m.config.sampling_rate)
            record(out, label="fake", group="neural_tts", generator="Meta MMS-TTS (VITS)", text=line,
                   source="generated locally with huggingface.co/facebook/mms-tts-eng", licence="CC BY-NC 4.0 (model)")
        del m
    except Exception as e:  # noqa: BLE001
        print("  mms fail", e)
    # SpeechT5
    try:
        from transformers import SpeechT5ForTextToSpeech, SpeechT5HifiGan, SpeechT5Processor
        import pyarrow.parquet as pq  # noqa: F401

        proc = SpeechT5Processor.from_pretrained("microsoft/speecht5_tts")
        m = SpeechT5ForTextToSpeech.from_pretrained("microsoft/speecht5_tts").eval()
        voc = SpeechT5HifiGan.from_pretrained("microsoft/speecht5_hifigan").eval()
        xv = _cmu_xvectors()
        for i, line in enumerate(TTS_LINES[2:10]):
            out = d / f"tts_speecht5_{i:02d}.wav"
            if not out.exists():
                spk = torch.tensor(xv[(i * 977) % len(xv)]).unsqueeze(0)
                with torch.no_grad():
                    w = m.generate_speech(proc(text=line, return_tensors="pt")["input_ids"], spk, vocoder=voc).numpy()
                sf.write(out, w / max(1e-6, np.abs(w).max()) * 0.9, 16000)
            record(out, label="fake", group="neural_tts", generator="Microsoft SpeechT5 + HiFi-GAN", text=line,
                   source="generated locally with huggingface.co/microsoft/speecht5_tts", licence="MIT (model)")
    except Exception as e:  # noqa: BLE001
        print("  speecht5 fail", e)
    # macOS say
    if sys.platform == "darwin":
        for i, (voice, line) in enumerate([("Samantha", TTS_LINES[3]), ("Daniel", TTS_LINES[8])]):
            out = d / f"tts_macos_say_{voice.lower()}.wav"
            if not out.exists():
                aiff = out.with_suffix(".aiff")
                subprocess.run(["say", "-v", voice, "-o", str(aiff), line], check=False)
                if aiff.exists():
                    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@22050", str(aiff), str(out)], check=False)
                    aiff.unlink(missing_ok=True)
            if out.exists():
                record(out, label="fake", group="classic_tts", generator=f"macOS say ({voice})", text=line,
                       source="generated locally (macOS speech synthesis)", licence="own recording")
    print("local tts done")


def _cmu_xvectors():
    """Speaker embeddings for SpeechT5 (Matthijs/cmu-arctic-xvectors, MIT)."""
    import numpy as np
    from huggingface_hub import HfApi

    repo = "Matthijs/cmu-arctic-xvectors"
    files = [s.rfilename for s in HfApi().dataset_info(repo).siblings]
    pq_files = [f for f in files if f.endswith(".parquet")]
    if pq_files:
        import pyarrow.parquet as pq

        t = pq.read_table(hf_file(repo, pq_files[0]))
        return [np.asarray(v, dtype=np.float32) for v in t.column("xvector").to_pylist()]
    # fallback: zip of .npy files
    import zipfile

    zf = [f for f in files if f.endswith(".zip")][0]
    z = zipfile.ZipFile(hf_file(repo, zf))
    out = []
    for name in z.namelist()[:2000:50]:
        if name.endswith(".npy"):
            out.append(np.load(io.BytesIO(z.read(name))).astype(np.float32))
    return out


# ------------------------------------------------------------------------------------------ video
def video_commons(titles: list[str]):
    d = OUT / "video/real"
    d.mkdir(parents=True, exist_ok=True)
    for title in titles:
        r = commons_api(dict(action="query", titles=title, prop="imageinfo", iiprop="url|size|mime|extmetadata"))
        pg = list(r["query"]["pages"].values())[0]
        ii = pg["imageinfo"][0]
        lic = ii.get("extmetadata", {}).get("LicenseShortName", {}).get("value", "")
        safe = "".join(c if c.isalnum() else "_" for c in title[5:60])
        ext = Path(ii["url"]).suffix
        out = d / f"commons_{safe}{ext}"
        if not out.exists():
            out.write_bytes(http_get(ii["url"], pause=4))
        record(out, label="real", group="talking_video", source=ii["descriptionurl"], licence=lic,
               author=_strip_html(ii.get("extmetadata", {}).get("Artist", {}).get("value", ""))[:120])
        time.sleep(2)
    print("video done")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="all")
    ap.add_argument("--video-title", action="append", default=[])
    a = ap.parse_args()
    steps = {
        "images": [images_ffhq, images_coco, images_tpdne, images_rapidata, images_commons_phone],
        "audio": [audio_librispeech, audio_unidata, audio_asvspoof, audio_local_tts, audio_librispeech_multi,
                  audio_fleurs, audio_asvspoof_speakers, audio_vocoded],
    }
    todo = []
    for k, fns in steps.items():
        if a.part in (k, "all"):
            todo += fns
    if a.part.startswith(("images_", "audio_")):
        todo = [globals()[a.part]]
    for fn in todo:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            print("STEP FAILED", fn.__name__, e)
        save_sources()
    if a.video_title:
        video_commons(a.video_title)
        save_sources()
    print("files recorded:", len(SOURCES))


if __name__ == "__main__":
    main()
