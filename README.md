# DeckShrink

Batch-slim .pptx/.docx/.xlsx files by re-encoding the pictures embedded
inside them — then prove every output: zip integrity, picture decode,
and byte-identical non-picture parts.

## Run (dev)

```
python3 gui.py                 # desktop app
python3 deck_shrink.py <file-or-folder> <outdir>
python3 test/acceptance_test.py
```

## How it works

An Office file is a zip of parts; the bulk is `*/media/*` pictures.
`deck_shrink.py` re-encodes each embedded JPEG/PNG/TIFF at a maximum
dimension and quality **without changing its format**, optionally
drops `docProps/thumbnail.jpeg` together with its package
relationship, and writes a new file. Re-check: `testzip()`, Pillow
decode of every output picture, and byte comparison of every
non-picture part against the original. Files that don't shrink are
reported honestly as already-optimized.

## Scope

Embedded pictures in macro-free Office files only. Standalone images
(ImageBatch) and PDFs are out of scope; GIF/BMP parts are left alone.
