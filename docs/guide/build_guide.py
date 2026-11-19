#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["segno>=1.5", "playwright>=1.40"]
# ///
"""Build the VERITAS Guide PDF:  docs/guide/guide.html + guide.css  ->  dist/VERITAS-Guide.pdf  (A4).

Rebuild (from the repo root; needs uv and Google Chrome, Microsoft Edge or a Playwright Chromium):

    uv run docs/guide/build_guide.py

Options:
    --links FILE   links file (default: ../_incoming/publish.json, next to the repo folder)
    --out FILE     output PDF (default: dist/VERITAS-Guide.pdf)
    --png DIR      also save one PNG per page (for checking the layout)
    --html FILE    also keep the filled, self-contained HTML

Tokens in guide.html and how they are filled from the links file
(keys: repo_url, release_zip_url, site_url, space_url, school):
    {{REPO_URL}} {{RELEASE_ZIP_URL}} {{SITE_URL}} {{SPACE_URL}} {{SCHOOL}}, plus
    {{ONLINE_URL}} = site_url, or space_url when the site is not known yet.
  * A value that is missing or still a "{{TOKEN}}" stays visible as an amber placeholder (and its QR code
    becomes a "link not set yet" box). Re-run this script once the real links are in the links file.
  * "school": null removes the school line on the cover (the <!--IF:school--> block).

The build fails (exit 1) if any page overflows or clips text, or if the PDF has more than 8 pages.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FONTS = REPO / "web" / "assets" / "fonts"
DEFAULT_LINKS = REPO.parent / "_incoming" / "publish.json"
DEFAULT_OUT = REPO / "dist" / "VERITAS-Guide.pdf"
MAX_PAGES = 8

DEFAULTS = {
    "repo_url": "https://github.com/Ahamedinmotion/veritas",
    "release_zip_url": "https://github.com/Ahamedinmotion/veritas/releases/latest/download/VERITAS-Windows.zip",
    "site_url": "{{SITE_URL}}",
    "space_url": "{{SPACE_URL}}",
    "school": None,
}
URL_TOKENS = {"REPO_URL": "repo_url", "RELEASE_ZIP_URL": "release_zip_url", "SITE_URL": "site_url",
              "SPACE_URL": "space_url", "ONLINE_URL": "online_url"}
TEXT_TOKENS = {"SCHOOL": "school"}

# family, style, weight range, file  (IBM Plex Sans is one variable font, 100-700)
FONT_FACES = [
    ("IBM Plex Sans", "normal", "100 700", "ibm-plex-sans-normal-300.woff2"),
    ("IBM Plex Sans Condensed", "normal", "400", "ibm-plex-sans-condensed-normal-400.woff2"),
    ("IBM Plex Sans Condensed", "normal", "500", "ibm-plex-sans-condensed-normal-500.woff2"),
    ("IBM Plex Sans Condensed", "normal", "600", "ibm-plex-sans-condensed-normal-600.woff2"),
    ("IBM Plex Sans Condensed", "normal", "700", "ibm-plex-sans-condensed-normal-700.woff2"),
    ("IBM Plex Mono", "normal", "400", "ibm-plex-mono-normal-400.woff2"),
    ("IBM Plex Mono", "normal", "500", "ibm-plex-mono-normal-500.woff2"),
    ("IBM Plex Mono", "normal", "600", "ibm-plex-mono-normal-600.woff2"),
    ("Instrument Serif", "normal", "400", "instrument-serif-normal-400.woff2"),
    ("Instrument Serif", "italic", "400", "instrument-serif-italic-400.woff2"),
]

# Runs in the page after layout: reports anything that overflows a page or is clipped.
CHECK_JS = r"""
() => {
  const problems = [];
  const name = (el) => `<${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${
      typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\s+/).join('.') : ''}>`;
  const pages = [...document.querySelectorAll('.page')];
  pages.forEach((pg, i) => {
    const n = i + 1, pr = pg.getBoundingClientRect();
    if (Math.abs(pr.height - 1122.5) > 2 || Math.abs(pr.width - 793.7) > 2)
      problems.push(`page ${n}: size ${pr.width.toFixed(1)} x ${pr.height.toFixed(1)} px, expected A4 (793.7 x 1122.5)`);
    const main = pg.querySelector('.pm') || pg.querySelector('.inner');
    if (main && main.scrollHeight > main.clientHeight + 1)
      problems.push(`page ${n}: content is ${main.scrollHeight - main.clientHeight} px taller than the page`);
    pg.querySelectorAll('*').forEach((el) => {
      if (el.closest('.bleed') || el.closest('svg') && el.tagName.toLowerCase() !== 'svg') return;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) return;
      if (r.right > pr.right + 0.5 || r.bottom > pr.bottom + 0.5 || r.left < pr.left - 0.5 || r.top < pr.top - 0.5)
        problems.push(`page ${n}: ${name(el)} sticks out of the page`);
      const cs = getComputedStyle(el);
      if (el !== pg && el !== main && cs.display !== 'inline' && el.clientWidth > 0 &&
          (el.scrollWidth > el.clientWidth + 1 || (cs.overflowY !== 'visible' && el.scrollHeight > el.clientHeight + 1)))
        problems.push(`page ${n}: ${name(el)} overflows its box (${el.scrollWidth}x${el.scrollHeight} in ${el.clientWidth}x${el.clientHeight})`);
    });
    if (main) {
      const mr = main.getBoundingClientRect();
      main.querySelectorAll('*').forEach((el) => {
        if (el.closest('svg') && el.tagName.toLowerCase() !== 'svg') return;
        const r = el.getBoundingClientRect();
        if (r.height > 0 && r.bottom > mr.bottom + 0.5) problems.push(`page ${n}: ${name(el)} is cut off at the bottom`);
        if (r.height > 0 && r.top < mr.top - 0.5) problems.push(`page ${n}: ${name(el)} is cut off at the top`);
      });
    }
  });
  const fonts = [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family.replace(/"/g, ''));
  return { problems, pages: pages.length, fonts: [...new Set(fonts)] };
}
"""


def known(v) -> bool:
    return isinstance(v, str) and bool(v.strip()) and not re.fullmatch(r"\{\{\s*\w+\s*\}\}", v.strip())


def pretty_url(url: str) -> str:
    return re.sub(r"^https?://", "", url.strip()).rstrip("/")


def load_links(path: Path) -> dict:
    links = dict(DEFAULTS)
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        links.update({k: data[k] for k in data if k in DEFAULTS})
        print(f"links: {path}")
    else:
        print(f"links: {path} not found - using defaults (site and space stay placeholders)")
    site, space = links.get("site_url"), links.get("space_url")
    links["online_url"] = site if known(site) else (space if known(space) else "{{SITE_URL}}")
    for k in ("repo_url", "site_url", "space_url", "online_url", "school"):
        v = links.get(k)
        print(f"  {k:<11} {v if known(v) else ('(removed)' if v is None and k == 'school' else '(placeholder)')}")
    return links


def font_css() -> str:
    out = []
    for fam, style, weight, fn in FONT_FACES:
        b64 = base64.b64encode((FONTS / fn).read_bytes()).decode("ascii")
        out.append(f"@font-face{{font-family:'{fam}';font-style:{style};font-weight:{weight};font-display:block;"
                   f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}")
    return "\n".join(out)


def qr_svg(url) -> str:
    if not known(url):
        return '<div class="missing">QR code appears when this link is set</div>'
    import segno
    return segno.make(url, error="m").svg_inline(scale=1, border=2, dark="#12151b", light="#f4f0e6", omitsize=True)


def fill(src: str, links: dict) -> str:
    # 1. drop the developer comment at the top
    src = re.sub(r"<!--\s*VERITAS Guide - source.*?-->\n?", "", src, count=1, flags=re.S)
    # 2. conditional blocks: removed when the value is null / empty (a "{{TOKEN}}" value keeps them, as a placeholder)
    def cond(m):
        v = links.get(m.group(1))
        return m.group(2) if (v is not None and str(v).strip()) else ""
    src = re.sub(r"<!--IF:(\w+)-->(.*?)<!--/IF:\1-->", cond, src, flags=re.S)
    # 3. QR codes
    src = src.replace("<!--QR:repo-->", qr_svg(links.get("repo_url")))
    src = src.replace("<!--QR:online-->", qr_svg(links.get("online_url")))
    # 4. links: full URL in href, short form in the text
    def href(m):
        v = links.get(URL_TOKENS[m.group(1)])
        return f'href="{html.escape(v.strip())}"' if known(v) else 'href="#"'
    src = re.sub(r'href="\{\{(' + "|".join(URL_TOKENS) + r')\}\}"', href, src)

    def text(m):
        tok = m.group(1)
        v = links.get(URL_TOKENS.get(tok) or TEXT_TOKENS[tok])
        if known(v):
            if tok in URL_TOKENS:  # short form, allowed to wrap only after a "/"
                return html.escape(pretty_url(v)).replace("/", "/<wbr>")
            return html.escape(v.strip())
        shown = "SITE_URL" if tok == "ONLINE_URL" else tok
        return f'<span class="ph-token">{{{{{shown}}}}}</span>'
    src = re.sub(r"\{\{(" + "|".join([*URL_TOKENS, *TEXT_TOKENS]) + r")\}\}", text, src)
    # 5. inline the fonts and the stylesheet so the HTML is self-contained
    css = (HERE / "guide.css").read_text(encoding="utf-8")
    src = re.sub(r'<link[^>]*data-build="fonts"[^>]*>', lambda _: f"<style>\n{font_css()}\n</style>", src)
    src = re.sub(r'<link[^>]*data-build="css"[^>]*>', lambda _: f"<style>\n{css}\n</style>", src)
    return src


def render_playwright(html_path: Path, pdf_path: Path, png_dir: Path | None):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, errors = None, []
        for kw in ({"channel": "chrome"}, {"channel": "msedge"}, {}):
            try:
                browser = p.chromium.launch(**kw)
                break
            except Exception as e:  # noqa: BLE001
                errors.append(f"{kw or 'bundled chromium'}: {str(e).splitlines()[0]}")
        if browser is None:
            raise RuntimeError("; ".join(errors))
        print(f"renderer: Playwright + Chromium {browser.version}")
        page = browser.new_page(viewport={"width": 794, "height": 1123})
        page.goto(html_path.as_uri())
        page.emulate_media(media="print")
        page.evaluate("document.fonts.ready.then(() => true)")
        page.wait_for_timeout(300)
        report = page.evaluate(CHECK_JS)
        page.pdf(path=str(pdf_path), prefer_css_page_size=True, print_background=True)
        if png_dir:
            png_dir.mkdir(parents=True, exist_ok=True)
            for i, el in enumerate(page.query_selector_all(".page"), 1):
                el.screenshot(path=str(png_dir / f"page-{i}.png"))
        browser.close()
    return report


def find_chrome() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "msedge", "chrome"):
        if shutil.which(name):
            return shutil.which(name)
    for c in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
              "/Applications/Chromium.app/Contents/MacOS/Chromium",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
        if Path(c).exists():
            return c
    return None


def render_cli(html_path: Path, pdf_path: Path):
    chrome = find_chrome()
    if not chrome:
        sys.exit("No Chrome, Edge or Chromium found. Install Google Chrome, or run: uvx playwright install chromium")
    print(f"renderer: {chrome} --headless --print-to-pdf (no layout check available)")
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--run-all-compositor-stages-before-draw", "--virtual-time-budget=15000",
                    f"--print-to-pdf={pdf_path}", html_path.as_uri()],
                   check=True, timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return None


def pdf_page_count(pdf: Path) -> int | None:
    data = pdf.read_bytes()
    n = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))
    return n or None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--links", type=Path, default=DEFAULT_LINKS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--png", type=Path, default=None)
    ap.add_argument("--html", type=Path, default=None)
    args = ap.parse_args()

    links = load_links(args.links)
    src = fill((HERE / "guide.html").read_text(encoding="utf-8"), links)
    left = sorted(set(re.findall(r"\{\{\w+\}\}", re.sub(r'<span class="ph-token">\{\{\w+\}\}</span>', "", src))))
    if left:
        print(f"warning: unknown tokens left in the HTML: {', '.join(left)}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="veritas-guide-") as tmp:
        html_path = Path(tmp) / "VERITAS-Guide.html"
        html_path.write_text(src, encoding="utf-8")
        if args.html:
            args.html.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(html_path, args.html)
        tmp_pdf = Path(tmp) / "VERITAS-Guide.pdf"
        try:
            report = render_playwright(html_path, tmp_pdf, args.png)
        except Exception as e:  # noqa: BLE001
            print(f"Playwright unavailable ({str(e).splitlines()[0][:160]}); falling back to the Chrome command line")
            report = render_cli(html_path, tmp_pdf)
        shutil.copyfile(tmp_pdf, args.out)

    ok = True
    if report:
        missing = {f for f, *_ in FONT_FACES} - set(report["fonts"])
        if missing:
            print(f"FAIL  fonts not loaded: {', '.join(sorted(missing))}")
            ok = False
        for p in report["problems"]:
            print(f"FAIL  {p}")
            ok = False
    pages = pdf_page_count(args.out) or (report or {}).get("pages")
    if pages and pages > MAX_PAGES:
        print(f"FAIL  {pages} pages (maximum {MAX_PAGES})")
        ok = False
    size_kb = args.out.stat().st_size / 1024
    print(f"{'OK  ' if ok else 'DONE WITH PROBLEMS  '}{args.out}  ({pages} pages, {size_kb:.0f} KB)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
