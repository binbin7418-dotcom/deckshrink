#!/usr/bin/env python3
"""DeckShrink seeded acceptance test.

Builds a minimal but structurally valid .pptx by hand (zip of parts)
with planted bloat:
  - a 4000x3000 noisy JPEG embedded at quality 95 (multi-MB)
  - a 3000x2000 noisy PNG
  - a docProps/thumbnail.jpeg part + its package relationship
Then asserts: output is much smaller, picture dims are capped, every
non-picture part is byte-identical, the thumbnail and its relationship
are gone, the zip is valid, every picture re-decodes, and the original
file is untouched (hash before/after).
"""
import hashlib
import os
import sys
import zipfile
from io import BytesIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PIL import Image
import random

from deck_shrink import run_deckshrink

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))


def noisy_image(w, h, fmt, quality=None):
    rnd = random.Random(7)
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            c = (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
            for dy in range(4):
                for dx in range(4):
                    px[x + dx, y + dy] = c
    buf = BytesIO()
    if fmt == "JPEG":
        im.save(buf, "JPEG", quality=quality or 95)
    else:
        im.save(buf, fmt)
    return buf.getvalue()


def photo_image(w, h):
    """Photo-like PNG: smooth gradients + fine grain (compresses like a
    real photo — big at full size, much smaller once downscaled)."""
    import numpy as np
    yy, xx = np.mgrid[0:h, 0:w]
    r = (128 + 100 * np.sin(xx / 90.0) + 27 * np.sin(yy / 31.0)).clip(0, 255)
    g = (120 + 90 * np.cos(yy / 70.0) + 30 * np.sin((xx + yy) / 47.0)).clip(0, 255)
    b = (110 + 100 * np.sin((xx - yy) / 120.0)).clip(0, 255)
    rng = np.random.default_rng(3)
    grain = rng.integers(-6, 7, size=(h, w, 1))
    arr = np.stack([r, g, b], axis=2).astype(np.int16) + grain
    im = Image.fromarray(arr.clip(0, 255).astype("uint8"), "RGB")
    buf = BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="jpeg" ContentType="image/jpeg"/><Default Extension="png" ContentType="image/png"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/></Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail" Target="docProps/thumbnail.jpeg"/></Relationships>"""

PRESENTATION = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldIdLst><p:sldId id="256" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></p:sldIdLst></p:presentation>"""

SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:pic><p:cNvPr id="2" name="big photo"/></p:pic></p:spTree></p:cSld></p:sld>"""

CORE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"><dc:title>Seed Deck</dc:title></cp:coreProperties>"""

os.makedirs(OUT, exist_ok=True)
src = os.path.join(OUT, "seed_deck.pptx")
jpg = noisy_image(4000, 3000, "JPEG", 95)
png = photo_image(3000, 2000)
thumb = noisy_image(640, 480, "JPEG", 90)
with zipfile.ZipFile(src, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", CONTENT_TYPES)
    z.writestr("_rels/.rels", RELS)
    z.writestr("ppt/presentation.xml", PRESENTATION)
    z.writestr("ppt/slides/slide1.xml", SLIDE)
    z.writestr("ppt/media/image1.jpg", jpg)
    z.writestr("ppt/media/image2.png", png)
    z.writestr("docProps/core.xml", CORE)
    z.writestr("docProps/thumbnail.jpeg", thumb)

size_in = os.path.getsize(src)
hash_before = hashlib.sha256(open(src, "rb").read()).hexdigest()
s = run_deckshrink([src], os.path.join(OUT, "slim"))
r = s["files"][0]
out_zip = zipfile.ZipFile(r["dst"])

check("seed deck is genuinely bloated", size_in > 3_000_000, f"{size_in} bytes")
check("output at least 50% smaller", r["size_out"] < size_in * 0.5,
      f"{r['size_in']} -> {r['size_out']}")
check("both images seen and slimmed", r["images_seen"] == 2 and r["images_slimmed"] == 2,
      f"{r['images_slimmed']}/{r['images_seen']}")
dims = []
for name in ("ppt/media/image1.jpg", "ppt/media/image2.png"):
    im = Image.open(BytesIO(out_zip.read(name)))
    dims.append(im.size)
check("picture dims capped at 1920", all(max(d) <= 1920 for d in dims), f"{dims}")
check("picture formats unchanged",
      out_zip.read("ppt/media/image1.jpg")[:2] == b"\xff\xd8"
      and out_zip.read("ppt/media/image2.png")[:4] == b"\x89PNG")
check("thumbnail part removed", "docProps/thumbnail.jpeg" not in out_zip.namelist())
rels_out = out_zip.read("_rels/.rels").decode()
check("thumbnail relationship removed", "thumbnail" not in rels_out)
same = (out_zip.read("ppt/slides/slide1.xml") == SLIDE.encode()
        and out_zip.read("[Content_Types].xml") == CONTENT_TYPES.encode()
        and out_zip.read("docProps/core.xml") == CORE.encode())
check("non-picture parts byte-identical", same and r["untouched_parts_ok"])
check("zip integrity + decode re-check", r["zip_ok"] and r["images_decode_ok"])
check("overall verdict PASS", s["verdict"])
check("original untouched",
      hashlib.sha256(open(src, "rb").read()).hexdigest() == hash_before)

passed = sum(1 for _, ok, _ in CHECKS if ok)
print(f"\n{passed}/{len(CHECKS)} checks passed")
sys.exit(0 if passed == len(CHECKS) else 1)
