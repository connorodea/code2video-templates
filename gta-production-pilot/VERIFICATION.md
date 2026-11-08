# Verified pilot execution — November 8, 2026

This record describes actual local execution of the included example. The output
folder contains `manifest.json` and `qa.json` with the measured results and file
hashes. Rendered media are intentionally excluded from git.

## Completed renders

| Run | Result | Canvas | Frames / rate | Duration | Checks |
| --- | --- | --- | --- | --- | --- |
| Full pilot, including ProRes layers | Passed | 1920×1080 | 720 / 30 fps | 24.000 s | 45/45 |
| Portrait review | Passed | 540×960 | 720 / 30 fps | 24.000 s | 30/30 |
| Local video + image + narration + Deepgram-format fixture | Passed | 960×540 | 720 / 30 fps | 24.000 s | 26/26 |

The full render completed in 97.4 seconds in this environment;
this is an observation, not a runtime guarantee. The one-command render was:

```bash
bash gta-production-pilot/make.command
```

The full-HD portrait example has layout/frame checks, but only the 540×960
portrait review was encoded during this session. No full-resolution portrait
ProRes render is claimed.

## Measured full export

- H.264 High review, 1920×1080, yuv420p, constant 30 fps, 720 decoded frames.
- ProRes 422 HQ clean master, 10-bit 4:2:2, 720 decoded frames.
- ProRes 4444 graphics master, decoded as yuva444p12le with alpha range 0–255.
  The sampled frame contained 81.24% fully transparent pixels.
- Rec.709 primaries, transfer and matrix metadata verified on all three videos.
- Each of four WAV stems: PCM16 stereo, 48 kHz, 1,152,000 samples per channel.
- Encoded review audio: -22.20 LUFS integrated and
  -7.50 dBTP measured true peak. No clipping detected.
- All seven narration/transition events matched frame-to-sample calculations.
- Native Flite word boundaries drove the demo captions. All normalized caption
  timestamps and punctuated words survived the separate Deepgram-shaped
  fixture round trip unchanged. That fixture was generated from the demo;
  it was not a response from a live Deepgram request.

Representative encoded frames were inspected for each scene, all transitions,
first/last frames, safe margins and caption placement. Portrait route framing
was also inspected. This establishes technical and frame-layout verification;
subjective listening approval remains unverified.

## Tests and source identity

```bash
python3 -m unittest discover -s gta-production-pilot/tests -v
```

All **29 tests passed** (audio/caption, XML handoff, real encoder and scene
contract tests). They include native local speech synthesis, real FFmpeg audio
and video handling, timestamp bounds/offsets, missing/short media rejection,
ProRes alpha, and a relocated XML writer running with Python `-I -S`.

The render manifest's Python source hashes were compared with the final renderer
files and matched. Runtime: Python 3.12.14, Pillow 13.0.0,
NumPy 2.3.5, jsonschema 4.26.0.
FFmpeg: ffmpeg version 7.1.5-0+deb13u1 Copyright (c) 2000-2026 the FFmpeg developers.

Review SHA-256:
`94599b8dfb3594582ca3f0efae47510397eae7d02689881a7bd4ec697066e171`

QA report SHA-256:
`3e7c85cde707895e6b7a420a0b97bfb91b36c93c4c2bf38525b66eed19cde52e`

## Explicit limits

- Resolve is not installed here. The generated XML passed structural/contract
  checks and references verified media, but application import is untested.
- Titles are editable in scene JSON and rerenderable. The exported graphics
  layer is rasterized; native Fusion Text+ titles and a .drp are not generated.
- No Claude orchestration API or live Deepgram API was called. Claude integration
  is the documented structured-input/CLI workflow.
- No reference video or actual gameplay was supplied; style remains provisional.
- No paid generation, public video upload, or merge was performed.
