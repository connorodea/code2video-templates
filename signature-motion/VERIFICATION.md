# Verification record

Checked 7 November 2026 on the implementation branch.

## Runtime

- Python 3.12.14
- Pillow 13.0.0
- FreeType 2.14.3
- ffmpeg version 7.1.5-0+deb13u1 Copyright (c) 2000-2026 the FFmpeg developers

## Executed checks

- `python3 -m unittest discover -s signature-motion/tests -v`: **13 tests passed**. Covers schema-independent input validation, missing sources, numeric bounds, frame timing, local assets, minimum preview dimensions, and frame seeking.
- Draft 2020-12 JSON Schema validated; all six example configurations conform. The CLI remains required for semantic checks such as exact aspect ratios and local files.
- All six example videos exported as **1080 × 1920, 30 fps, 8 seconds, 240 frames**, H.264. FFprobe checked these values and actual encoded frames were decoded for visual review.
- Scene frames evaluated at beginning, middle and end for portrait, landscape and square, with out-of-order frame equality checked. This is not a full MP4 export of every aspect or input combination.
- Prism accepted three relative local image paths in an end-to-end render. A supplied one-second test tone was padded to a six-second AAC track; the output contained 144 video frames at 24 fps.
- The combined silent preview reel is **48 seconds, 1440 frames, 1080 × 1920, 30 fps**.
- Seven advanced recipe entries have continuous proposed beat timing and are explicitly marked `status: design`, `runtime_supported: false`.
- `inspect_reference.py` ran on three local portfolio excerpts, producing metadata and timestamped frame contact sheets. Reference media stays outside the repository.

## Scope

The six local starter renderers and their input/output contract were exercised. No external video editor was connected. The seven reference-led recipes and twelve additional concepts are design work. Source-reference presence does not verify factual claims. Font, platform, encoder and dependency differences can affect reproducibility; production workers should pin their runtime.

Rendered media is excluded from Git. Reproduce it using the README commands.
