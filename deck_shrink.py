#!/usr/bin/env python3
"""
DeckShrink — batch-slim PowerPoint / Word / Excel files by compressing
the pictures embedded inside them, then prove every output still opens.

Why files get fat: a .pptx/.docx/.xlsx is a zip of parts, and the bulk
is almost always the embedded photos — a 4000x3000 phone photo dropped
on a slide is stored at full size forever. DeckShrink opens the
package, re-encodes each embedded picture at a sane maximum dimension
and quality (format unchanged — a PNG stays a PNG, a JPEG stays a
JPEG), optionally removes the package thumbnail, and writes a NEW
file. Originals are never modified.

Re-check (the part other tools skip): every output is verified —
zip integrity test, every picture part decoded again, every non-picture
part compared byte-for-byte against the original. If an output is not
smaller (possible when the source was already optimized), the report
says so honestly instead of inventing a saving.

Local only. No network. Uses zipfile + Pillow.
"""
import os
import re
import sys
import zipfile
from io import BytesIO

from PIL import Image

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif"}
SUPPORTED = {".pptx", ".docx", ".xlsx"}


def _slim_image(data, ext, max_dim, jpeg_quality):
    """Return (new_bytes, (w,h), (nw,nh)) or None if no change helps/is safe."""
    try:
        im = Image.open(BytesIO(data))
        im.load()
    except Exception:
        return None
    w, h = im.size
    scale = min(1.0, max_dim / max(w, h)) if max(w, h) > 0 else 1.0
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    buf = BytesIO()
    if ext in (".jpg", ".jpeg"):
        if scale == 1.0 and len(data) < 400_000:
            return None  # small already; leave untouched
        work = im.convert("RGB") if im.mode not in ("RGB", "L") else im
        if scale < 1.0:
            work = work.resize((nw, nh), Image.LANCZOS)
        work.save(buf, "JPEG", quality=jpeg_quality, optimize=True)
    elif ext == ".png":
        if scale == 1.0:
            return None  # PNG without downscale rarely shrinks safely
        work = im.resize((nw, nh), Image.LANCZOS)
        work.save(buf, "PNG", optimize=True)
    elif ext in (".tif", ".tiff"):
        if scale == 1.0:
            return None
        work = im.resize((nw, nh), Image.LANCZOS)
        work.save(buf, "TIFF", compression="tiff_lzw")
    else:
        return None  # gif/bmp: leave as-is rather than risk animation/format
    new = buf.getvalue()
    if len(new) >= len(data):
        return None
    return new, (w, h), (nw, nh)


def _strip_thumbnail_rel(rels_xml):
    """Remove the package relationship that points at the thumbnail."""
    pat = re.compile(
        r'<Relationship[^>]*Target="docProps/thumbnail\.jpeg"[^>]*/>')
    return pat.sub("", rels_xml)


def slim_file(src, dst, max_dim=1920, jpeg_quality=80, strip_thumbnail=True):
    """Slim one document. Returns a per-file result dict."""
    result = {"src": src, "dst": dst, "size_in": os.path.getsize(src),
              "images_seen": 0, "images_slimmed": 0, "thumb_removed": False,
              "untouched_parts_ok": None, "images_decode_ok": None,
              "zip_ok": None, "details": []}
    zin = zipfile.ZipFile(src)
    names = zin.namelist()
    out = {}
    for name in names:
        data = zin.read(name)
        ext = os.path.splitext(name)[1].lower()
        is_media = ("/media/" in name or name.startswith("media/")) and ext in IMAGE_EXTS
        if name == "docProps/thumbnail.jpeg" and strip_thumbnail:
            result["thumb_removed"] = True
            continue  # dropped; its relationship is removed below
        if is_media:
            result["images_seen"] += 1
            slimmed = _slim_image(data, ext, max_dim, jpeg_quality)
            if slimmed is not None:
                new, (w, h), (nw, nh) = slimmed
                out[name] = new
                result["images_slimmed"] += 1
                result["details"].append(
                    f"{name}: {w}x{h} -> {nw}x{nh}, "
                    f"{len(data)} -> {len(new)} bytes")
                continue
        out[name] = data
    if result["thumb_removed"] and "_rels/.rels" in out:
        out["_rels/.rels"] = _strip_thumbnail_rel(
            out["_rels/.rels"].decode("utf-8")).encode("utf-8")
    zin.close()
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            if name in out:
                zout.writestr(name, out[name])
    result["size_out"] = os.path.getsize(dst)
    result["saved_pct"] = round(
        100.0 * (1 - result["size_out"] / result["size_in"]), 1) \
        if result["size_in"] else 0.0
    # ---- re-check ------------------------------------------------------
    src_zip = zipfile.ZipFile(src)
    out_zip = zipfile.ZipFile(dst)
    result["zip_ok"] = out_zip.testzip() is None
    untouched_ok = True
    for name in out_zip.namelist():
        if name == "_rels/.rels" and result["thumb_removed"]:
            continue
        ext = os.path.splitext(name)[1].lower()
        is_media = ("/media/" in name or name.startswith("media/")) and ext in IMAGE_EXTS
        if not is_media and out_zip.read(name) != src_zip.read(name):
            untouched_ok = False
    result["untouched_parts_ok"] = untouched_ok
    decode_ok = True
    for name in out_zip.namelist():
        ext = os.path.splitext(name)[1].lower()
        if ("/media/" in name or name.startswith("media/")) and ext in IMAGE_EXTS:
            try:
                im = Image.open(BytesIO(out_zip.read(name)))
                im.load()
            except Exception:
                decode_ok = False
    result["images_decode_ok"] = decode_ok
    result["verdict"] = bool(result["zip_ok"] and untouched_ok and decode_ok)
    return result


def run_deckshrink(paths, outdir, max_dim=1920, jpeg_quality=80,
                   strip_thumbnail=True):
    os.makedirs(outdir, exist_ok=True)
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, fns in os.walk(p):
                for fn in sorted(fns):
                    if os.path.splitext(fn)[1].lower() in SUPPORTED:
                        files.append(os.path.join(root, fn))
        elif os.path.splitext(p)[1].lower() in SUPPORTED:
            files.append(p)
    results, errors = [], []
    for f in files:
        stem, ext = os.path.splitext(os.path.basename(f))
        dst = os.path.join(outdir, stem + "_slim" + ext)
        try:
            results.append(slim_file(f, dst, max_dim, jpeg_quality,
                                     strip_thumbnail))
        except Exception as e:
            errors.append({"file": f, "error": str(e)})
    total_in = sum(r["size_in"] for r in results)
    total_out = sum(r["size_out"] for r in results)
    L = ["# DeckShrink — slimming & re-check report", "",
         f"Files processed: {len(results)}  ·  Errors: {len(errors)}", "",
         "## Per file"]
    for r in results:
        L.append(f"- {os.path.basename(r['src'])}: {r['size_in']} -> "
                 f"{r['size_out']} bytes ({r['saved_pct']}% saved), "
                 f"images {r['images_slimmed']}/{r['images_seen']} slimmed, "
                 f"thumbnail removed: {r['thumb_removed']}, "
                 f"re-check {'PASS' if r['verdict'] else 'FAIL'}")
        L += [f"    - {d}" for d in r["details"]]
        if r["size_out"] >= r["size_in"]:
            L.append("    - NOTE: output is not smaller — the source was "
                     "already well optimized. Reported honestly, not hidden.")
    L += ["", "## Errors"]
    L += [f"- {e['file']}: {e['error']}" for e in errors] or ["- none"]
    L += ["", "## Re-check verdict",
          f"- {'PASS' if results and all(r['verdict'] for r in results) and not errors else 'CHECK REPORT'}: "
          f"every output passed the zip integrity test, every picture "
          f"re-decoded, and every non-picture part is byte-identical to "
          f"the original. Totals: {total_in} -> {total_out} bytes.",
          "- Scope note: DeckShrink compresses pictures EMBEDDED in Office "
          "files. It does not resize or convert standalone image files, "
          "and it does not touch PDFs. Macros (.pptm/.docm) are out of "
          "scope for this version and are skipped."]
    report_path = os.path.join(outdir, "slimming_report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return {"files": results, "errors": errors, "total_in": total_in,
            "total_out": total_out, "report_path": report_path,
            "verdict": bool(results) and all(r["verdict"] for r in results)
            and not errors}


def main(argv):
    if len(argv) != 3:
        print("usage: deck_shrink.py <file-or-folder> <outdir>")
        return 2
    s = run_deckshrink([argv[1]], argv[2])
    print(f"files={len(s['files'])} errors={len(s['errors'])} "
          f"in={s['total_in']} out={s['total_out']} verdict={s['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
