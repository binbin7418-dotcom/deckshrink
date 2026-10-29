# DeckShrink — Acceptance

Seeded test (system python3 + Pillow): `test/acceptance_test.py`
Full output: `test/acceptance_results.txt`

**Result: 11/11 checks passed.**

The test builds a structurally valid .pptx by hand (zip of parts)
with planted bloat: a 4000×3000 quality-95 JPEG, a 3000×2000
photo-like PNG, and a `docProps/thumbnail.jpeg` part with its package
relationship — 18,379,495 bytes total.

Verified:
- Output 4,591,988 bytes (75% saved, ≥50% required)
- Both pictures slimmed, dimensions capped at 1920 px, formats
  unchanged (JPEG magic bytes / PNG signature intact)
- Thumbnail part removed AND its `_rels/.rels` relationship removed
- Non-picture parts byte-identical to the source
- Zip integrity + picture re-decode re-checks pass; verdict PASS
- Original file untouched (SHA-256 before/after identical)
- GUI + engine compile clean (`py_compile`)
