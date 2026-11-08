---
name: gta-production-pilot
description: >
  Render a complete local GTA channel production pilot from a structured JSON
  scene specification: configurable titles, synthetic or licensed footage,
  route/telemetry motion graphics, transitions, synchronized narration and
  timed captions, music, effects, H.264 review and layered ProRes/PCM/Final Cut
  Pro 7 XML handoff for DaVinci Resolve. Accept Deepgram prerecorded word JSON,
  normalized timed words, or SRT. Use for a reusable GTA production starting
  point or a local agentic video workflow; no paid services or publication calls.
license: "MIT; system dependencies and fonts retain their licenses, see THIRD_PARTY_NOTICES.md"
metadata:
  version: "1.0.0"
  varg.cost.typical: "0 generation credits (local render)"
  varg.runtime.typical: "Machine and canvas dependent; 24 s example, preview-only available"
  varg.models: "Local Flite SLT demonstration voice; no remote model calls"
  varg.outputs: "H.264 MP4, ProRes HQ and 4444 alpha MOV, PCM WAV stems, xmeml v5, SRT, words JSON, manifest and QA"
  varg.engine: "Python + Pillow + NumPy + FFmpeg"
---

# GTA production pilot

Read the repository `AGENTS.md`, this file, `README.md`, `schema.json`, and the
example before authoring a job. Work inside this template's structured inputs;
routine content and style changes do not require changing the renderer.

## Inputs and boundaries

- A job brief: intended topic, facts/sources, narration text, format, and duration.
- Optional reference video for creative direction. Until supplied, retain the
  configurable demonstration style and describe it as provisional.
- Authorized local footage or images, with truthful `license` and `credit`.
  Otherwise use the existing synthetic backgrounds; do not fetch gameplay.
- Local narration plus timings from the **same** recording, or the synthetic
  demo voice. Accept native Deepgram JSON, word JSON, or SRT. SRT word positions
  are estimated within the cue, which must be disclosed.

The example is sufficient to render without asking for these optional inputs.
Use `project.demo: true` for demonstrations and make no factual gameplay claims
from the synthetic route or values. Respect the user's current brief. Do not
call paid generation services, publish, or merge without explicit approval of
the concrete proposed action. No such calls are needed to run this template.

## Fast path

From the repository root, with local dependencies installed:

```bash
bash gta-production-pilot/make.command
```

This creates `gta-production-pilot/out/pilot/` with the review, handoff, captions
and verification records. `make.command` reports missing Python dependencies;
installation is explicit:

```bash
python3 -m pip install -r gta-production-pilot/requirements.txt
```

FFmpeg/ffprobe, local fonts, and Flite SLT libraries are additional system
dependencies. See `README.md`. No API keys, Bun, or browser are required.

## Author a job

1. Copy `examples/pilot.json` or `examples/pilot-vertical.json` into a separate
   job directory. Keep input files outside its render output directory.
2. Change `project`, `video`, `style`, `narration`, `captions`, `audio`, and
   `scenes` as needed. `schema.json` is the authoritative input contract.
3. Keep scenes contiguous. Use integer frame indices for cuts and durations,
   seconds for word timings. A transition occupies the first frames of the
   incoming scene and does not extend the timeline. Supported rates are
   integer 24/25/30/50/60 fps.
4. Preserve exact spoken caption text. Deepgram words are at
   `results.channels[channel].alternatives[0].words`; no transcription request
   is made. `offset_seconds` shifts audio and timestamps together. Do not invent
   word timing or silently replace supplied timing.
5. For local backgrounds, select `kind: video` or `image`, a local path, `fit:
   cover` or `contain`, and actual rights/credit metadata. Source video audio
   is muted; short footage fails rather than looping.
6. Shorten or reflow text that fails layout checks. Keep fonts and palette
   configurable until the reference direction is accepted.

`CLAUDE-PROMPT.md` contains a ready-to-use agent task with the same boundaries.

## Validate, render, inspect

Example job commands from the repository root:

```bash
python3 gta-production-pilot/render.py --spec jobs/example/scene-spec.json --validate
python3 gta-production-pilot/render.py --spec jobs/example/scene-spec.json --out jobs/example/still --still 2.4
python3 gta-production-pilot/render.py --spec jobs/example/scene-spec.json --out jobs/example/render
```

For quick iteration, add `--size 960x540 --preview-only` and use a separate
output directory. `--preview-only` skips ProRes and XML, while still producing
audio, captions, review and QA. `--still` writes one JPEG after preparing the
audio/captions; a still is not evidence of a complete render. Use `--overwrite`
only to regenerate a directory created by this renderer.

Run long renders in a background process with a log, check its exit status,
and keep the user informed. Require all of the following before claiming a
verified render:

- The rendering process exits successfully.
- Both `qa.json` and `manifest.json` report `status: passed` for that run.
- Representative frames from the actual encoded `review.mp4` have been
  inspected, including every scene and transition, first/last frames, and
  caption layout. `contact-sheet.jpg` and `frames/` are generated for this.
- Audio intelligibility, mix and perceptual synchronization have been reviewed
  when playback is available. If playback was unavailable, report the measured
  timing checks and leave listening approval unverified.

For implementation changes, run:

```bash
python3 -m unittest discover -s gta-production-pilot/tests -v
```

Tests validate contracts, timestamps, routing and source handling. They do not
replace a completed render. Avoid attributing a prior render to changed source;
the manifest contains source hashes and actual output properties.

## Resolve handoff

The full render provides `timeline.xml` (FCP7 `xmeml` v5), `captions.srt`, and:

- V1: `resolve/clean.mov`, ProRes 422 HQ background.
- V2: `resolve/graphics.mov`, ProRes 4444 with straight alpha, containing titles,
  motion graphics and transition overlays, without captions.
- Three separate 48 kHz stereo PCM16 stems: `narration.wav`, `music.wav`,
  `sfx.wav`. The XML represents these as six linked mono channel tracks.

All masters start at frame zero and have the full timeline duration. Video is
split into scene clips referencing these masters. Import SRT separately at the
timeline's 00:00:00:00 start; it is editable in Resolve. Animated word highlights
appear in the review only. Do not add the review mix alongside the stems.

If the export moves, regenerate its absolute media URLs using the stdlib-only
relocation command:

```bash
python3 gta-production-pilot/handoff.py --out /path/to/export
```

An included standalone copy can run as `python3 handoff.py --out .` within the
export. It reads `resolved-spec.json` and references local `resolve/` media.

Titles remain editable in JSON and through rerendering. This template does not
create native Fusion titles or a `.drp` project. XML tests and media QA do not
prove successful Resolve import. Report `not_application_verified` until the
timeline is actually opened and checked in Resolve.

## Handover

Return the review and handoff paths, canvas/rate/duration/frame count, timing
source, actual QA status, representative frame findings, and remaining
verification limits. State whether narration is synthetic or supplied, whether
word timing is exact or interpolated, and whether Resolve import was tested.
Keep generated media out of git. Do not host or publish a preview unless the
user authorizes that action.
