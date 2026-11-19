# VERITAS Guide (PDF)

Source of `dist/VERITAS-Guide.pdf` (shipped in the release zip as `VERITAS Guide.pdf`): a 7-page A4 field guide
for the booth team (product, setup, booth plan, judges' questions, troubleshooting).

Rebuild from the repo root:

```
uv run docs/guide/build_guide.py
```

- `guide.html` + `guide.css` hold the content and the print layout; fonts come from `web/assets/fonts`.
- Links are read from `../_incoming/publish.json` (`repo_url`, `site_url`, `space_url`, `school`); use
  `--links FILE` for another file. Unknown links stay visible as amber `{{SITE_URL}}`-style placeholders, and their
  QR code becomes a "link not set yet" box. `"school": null` removes the school line on the cover.
- Needs `uv` and Google Chrome (or Edge, or a Playwright Chromium). The script checks every page for overflow and
  clipped text and fails if there is any, or if the PDF has more than 8 pages.
- `--png DIR` also saves one PNG per page for a quick visual check.

Every number in the guide must match `web/data/results.json`, `docs/PITCH.md` and `docs/JUDGE_QA.md`.
