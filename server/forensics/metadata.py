"""Metadata forensics: EXIF, XMP, PNG text chunks, C2PA content credentials.

Cameras write EXIF (make, model, exposure, timestamps). AI tools often write their own tags - Stable
Diffusion front-ends store the whole prompt in a PNG 'parameters' chunk, ComfyUI stores its 'workflow',
and many generators add an IPTC 'trainedAlgorithmicMedia' source type or a C2PA manifest.
Missing metadata is NOT proof of anything (messaging apps strip it), so it only nudges the score.
"""
from __future__ import annotations

import re

from PIL import ExifTags, Image

from .base import calibrated, make_test

NAME = "Metadata & Provenance"
EXPLAIN = ("Digital files carry hidden labels: cameras record make, model, lens and capture time in EXIF, "
           "while many AI tools embed their prompt, software name or a C2PA 'content credential'. "
           "Metadata is easy to strip or fake, so it is supporting evidence rather than proof.")

# AI-tool markers. These are matched ONLY against provenance fields (which program wrote the file, IPTC digital
# source type, AI front-end parameter chunks, C2PA manifests) - never against free text such as a caption or
# description, where ordinary words ("runway", "firefly", "imagen" = Spanish for image) would cause false alarms.
AI_PATTERNS = [
    (r"trainedalgorithmicmedia", "IPTC source type: trained algorithmic media (AI)"),
    (r"compositesynthetic|compositewithtrainedalgorithmicmedia|/algorithmicmedia", "IPTC source type: synthetic composite"),
    (r"stable[\s_-]?diffusion|\bsd[\s_-]?xl\b|\bsdxl\b", "Stable Diffusion"),
    (r"midjourney", "Midjourney"),
    (r"dall[\s·\-_]?e[\s\-_]?[23]?\b|\bopenai\b|chatgpt|gpt-4o|gpt-image", "OpenAI (DALL-E / ChatGPT)"),
    (r"adobe firefly", "Adobe Firefly"),
    (r"made with google ai|google imagen|\bimagen [234]\b|gemini image|nano[\s-]?banana", "Google AI"),
    (r"comfyui|\"class_type\"", "ComfyUI workflow"),
    (r"automatic1111|negative prompt:|cfg scale:|sampler:", "Stable Diffusion WebUI parameters"),
    (r"novelai|leonardo\.ai|ideogram|playground ai|runwayml|runway gen-?[234]|black forest labs|flux\.1", "AI image service"),
    (r"\bfaceapp\b|\bremini\b|\breface\b", "AI face-editing app"),
    (r"openai sora|google veo|kling ai|pika labs|luma dream machine", "AI video generator"),
]
EDIT_PATTERNS = [
    r"photoshop", r"\bgimp\b", r"snapseed", r"picsart", r"\bcanva\b", r"facetune", r"pixlr", r"affinity photo",
    r"paint\.net", r"photopea", r"lightroom", r"capture one", r"luminar",
]
# EXIF / text-chunk keys that describe the producing software or the provenance of the pixels
PROVENANCE_EXIF = ("Software", "HostComputer", "ProcessingSoftware")
PROVENANCE_CHUNKS = ("software", "parameters", "prompt", "workflow", "generator", "creator tool", "source",
                     "sd-metadata", "invokeai_metadata", "dream", "c2pa")
XMP_PROVENANCE = re.compile(
    r"(?:xmp:CreatorTool|photoshop:Credit|Iptc4xmpExt:DigitalSourceType|plus:DigitalSourceType|"
    r"DigitalSourceType|tiff:Software|xmp:Software|crs:ProcessVersion|exif:Software)"
    r"""(?:\s*=\s*["']([^"']*)["']|>\s*(?:<[^>]*>\s*)*([^<]*))""", re.I)
KEEP = ["Make", "Model", "LensModel", "Software", "DateTimeOriginal", "DateTime", "ExposureTime", "FNumber",
        "ISOSpeedRatings", "PhotographicSensitivity", "FocalLength", "Artist", "ImageDescription",
        "ExifImageWidth", "ExifImageHeight", "ColorSpace", "Flash", "WhiteBalance", "HostComputer"]


def _fmt(v):
    if isinstance(v, bytes):
        v = v.decode("utf-8", "ignore").strip("\x00 ")
    if isinstance(v, tuple):
        v = "/".join(str(x) for x in v)
    try:
        if hasattr(v, "numerator") and hasattr(v, "denominator"):
            f = float(v)
            if 0 < f < 1:
                return f"1/{round(1 / f)}"
            return f"{f:g}"
    except Exception:  # noqa: BLE001
        pass
    s = str(v).strip()
    return s[:80]


def read_exif(img: Image.Image) -> dict:
    out = {}
    try:
        ex = img.getexif()
    except Exception:  # noqa: BLE001
        return out
    if not ex:
        return out
    items = dict(ex.items())
    for ifd in (ExifTags.IFD.Exif, ExifTags.IFD.GPSInfo):
        try:
            sub = ex.get_ifd(ifd)
            if ifd == ExifTags.IFD.GPSInfo:
                if sub:
                    out["_gps"] = True
            else:
                items.update(sub)
        except Exception:  # noqa: BLE001
            pass
    for k, v in items.items():
        name = ExifTags.TAGS.get(k, str(k))
        if name in KEEP:
            out[name] = _fmt(v)
    return out


def collect_text(img: Image.Image, raw: bytes) -> tuple[dict, str]:
    """PNG/WebP text chunks + XMP packet + a cheap scan of the raw bytes for provenance markers."""
    chunks = {}
    for k, v in (img.info or {}).items():
        if isinstance(v, (str, bytes)) and k not in ("icc_profile", "exif", "dpi", "transparency"):
            s = v.decode("utf-8", "ignore") if isinstance(v, bytes) else v
            chunks[k] = s[:4000]
    xmp = ""
    m = re.search(rb"<x:xmpmeta.*?</x:xmpmeta>", raw[:2_000_000], re.S)
    if m:
        xmp = m.group(0).decode("utf-8", "ignore")[:20000]
    blob = " ".join(chunks.values()) + " " + xmp
    return chunks, blob


def provenance_text(exif: dict, chunks: dict, xmp: str) -> str:
    """Only the fields that say which program made the file (see AI_PATTERNS)."""
    parts = [exif.get(k, "") for k in PROVENANCE_EXIF]
    for k, v in chunks.items():
        if k.lower() in PROVENANCE_CHUNKS or k.lower().startswith(("sd:", "comfy", "invoke")):
            parts.append(v)
    for m in XMP_PROVENANCE.finditer(xmp):
        parts.append(m.group(0))
    return " ".join(p for p in parts if p)


def analyse(img: Image.Image, raw: bytes) -> dict:
    exif = read_exif(img)
    chunks, blob = collect_text(img, raw)
    xmp = ""
    m = re.search(r"<x:xmpmeta.*?</x:xmpmeta>", blob, re.S)
    if m:
        xmp = m.group(0)
    head = raw[:3_000_000]
    c2pa = (b"jumb" in head and b"c2pa" in head) or b"c2pa.claim" in head or b"urn:c2pa" in head
    low = provenance_text(exif, chunks, xmp).lower()
    if c2pa:
        # only look for long, unambiguous provenance strings inside the binary manifest
        hl = head.lower()
        for marker in (b"trainedalgorithmicmedia", b"compositesynthetic", b"openai", b"dall-e", b"dall\xc2\xb7e",
                       b"adobe firefly", b"made with google ai", b"midjourney", b"stable diffusion"):
            if marker in hl:
                low += " " + marker.decode("latin-1")
    ai_hits = []
    for pat, label in AI_PATTERNS:
        if re.search(pat, low):
            ai_hits.append(label)
    if "parameters" in chunks and re.search(r"steps:\s*\d+", chunks["parameters"].lower()):
        ai_hits.append("Stable Diffusion 'parameters' chunk (prompt + sampler settings)")
    if "prompt" in chunks and "{" in chunks.get("prompt", ""):
        ai_hits.append("ComfyUI prompt graph")
    ai_hits = list(dict.fromkeys(ai_hits))
    software = exif.get("Software", "") + " " + chunks.get("Software", "")
    edit_hits = [p.replace("\\b", "").replace("\\", "") for p in EDIT_PATTERNS if re.search(p, software.lower() + " " + low)]
    camera = bool(exif.get("Make") or exif.get("Model"))
    capture = bool(exif.get("DateTimeOriginal"))
    exposure = bool(exif.get("ExposureTime") or exif.get("FNumber") or exif.get("ISOSpeedRatings") or exif.get("PhotographicSensitivity"))

    flags = []
    if camera:
        flags.append(f"Camera: {(exif.get('Make', '') + ' ' + exif.get('Model', '')).strip()}")
    if capture:
        flags.append(f"Captured {exif['DateTimeOriginal']}")
    if exif.get("_gps"):
        flags.append("GPS location present (hidden for privacy)")
    if not exif:
        flags.append("No camera EXIF")
    elif not camera:
        flags.append("EXIF present but no camera make/model")
    if software.strip():
        flags.append(f"Software: {software.strip()[:60]}")
    for h in ai_hits:
        flags.append(f"AI marker: {h}")
    if c2pa:
        flags.append("C2PA content credentials present")
    if chunks and not ai_hits:
        keys = [k for k in chunks if k.lower() not in ("xmp", "xml:com.adobe.xmp")][:4]
        if keys:
            flags.append("Text chunks: " + ", ".join(keys))
    exif_out = {k: v for k, v in exif.items() if not k.startswith("_")}
    for k in ("parameters", "prompt", "Software", "Comment", "Description"):
        if k in chunks and k not in exif_out:
            exif_out[k] = chunks[k][:160]
    return {"exif": exif_out, "flags": flags, "ai_hits": ai_hits, "edit_hits": edit_hits, "camera": camera,
            "capture": capture, "exposure": exposure, "c2pa": c2pa, "has_any": bool(exif or chunks or blob.strip())}


def run(img: Image.Image, raw: bytes) -> tuple[dict, dict]:
    md = analyse(img, raw)
    if md["ai_hits"]:
        raw_s, finding = 97, f"AI-tool marker found in metadata: {md['ai_hits'][0][:48]}."
    elif md["edit_hits"]:
        raw_s, finding = 55, f"File was processed by editing software ({md['edit_hits'][0]})."
    elif md["camera"] and md["capture"] and md["exposure"]:
        raw_s, finding = 8, "Full camera EXIF: make, model, exposure and capture time intact."
    elif md["camera"]:
        raw_s, finding = 22, "Camera make/model present but some capture details missing."
    elif md["c2pa"]:
        raw_s, finding = 30, "Content-credential (C2PA) manifest present; no AI claim found."
    elif md["has_any"]:
        raw_s, finding = 42, "Some metadata, but no camera information."
    else:
        raw_s, finding = 45, "No metadata at all; stripped by an app, or never a camera photo."
    score = calibrated("metadata", raw_s)
    test = make_test("metadata", NAME, "metadata", score=score, finding=finding, explain=EXPLAIN,
                     metrics={"exif_fields": len(md["exif"]), "camera_exif": md["camera"], "ai_markers": len(md["ai_hits"]),
                              "c2pa": md["c2pa"], "raw": raw_s})
    return test, {"exif": md["exif"], "flags": md["flags"], "ai_marker": bool(md["ai_hits"])}
