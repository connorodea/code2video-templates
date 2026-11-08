# GTA production pilot

A local, reusable 24-second video production pilot: structured scene input,
synthetic city footage, editable titles, timed captions, route and telemetry
graphics, transitions, narration, music, sound effects, and a layered export for
DaVinci Resolve. The visual direction is a configurable demonstration pending a
reference video and authorized gameplay footage.

This is a runnable production template. Claude can write its JSON specification;
existing Deepgram transcription responses can supply word timestamps. The
renderer makes no LLM, transcription, paid generation, or publishing calls.

## Render the example

From the repository root, install the local dependencies once:

```bash
python3 -m pip install -r gta-production-pilot/requirements.txt
```

Requirements: Python 3.10+, Pillow, NumPy, jsonschema, FFmpeg and ffprobe on PATH,
DejaVu Sans regular/bold fonts or explicit local font paths, and local Flite SLT
voice libraries for the synthetic narration. FFmpeg needs `libx264`,
`prores_ks`, AAC, and PCM support. No Bun, Chrome, API key, or generation credits
are required for this template. Dependency installation is explicit; the
renderer does not install software or download assets.

Synthetic speech requires discoverable `flite`, `flite_usenglish`,
`flite_cmulex`, and `flite_cmu_us_slt` shared libraries (provided by the local
`libflite1` package on the tested Linux system). There is no remote or silent
fallback. If the libraries are unavailable, install the appropriate local
Flite package or use `narration.mode: "file"` with your own audio and timings.

Run the complete example:

```bash
bash gta-production-pilot/make.command
```

The default canvas is 1920×1080, 30 fps, 720 frames / 24 seconds. Outputs go to
`gta-production-pilot/out/pilot/`. Rendering time and ProRes file size depend on
the machine and canvas. Use a unique output directory for each job.

Equivalent explicit command:

```bash
python3 gta-production-pilot/render.py --spec gta-production-pilot/examples/pilot.json --out gta-production-pilot/out/pilot
```

Useful alternatives:

```bash
# Validate the specification, source media and basic text layout.
python3 gta-production-pilot/render.py --spec gta-production-pilot/examples/pilot.json --validate

# Faster review; same timing, smaller canvas, no ProRes masters or XML.
python3 gta-production-pilot/render.py --spec gta-production-pilot/examples/pilot.json --out gta-production-pilot/out/preview --size 960x540 --preview-only

# Inspect a single moment, including the actual timed captions.
python3 gta-production-pilot/render.py --spec gta-production-pilot/examples/pilot.json --out gta-production-pilot/out/still --still 2.4

# Separate vertical example.
python3 gta-production-pilot/render.py --spec gta-production-pilot/examples/pilot-vertical.json --out gta-production-pilot/out/vertical

# Rebuild a directory previously created by this renderer.
bash gta-production-pilot/make.command --overwrite
```

`--still` takes seconds and writes `still.jpg`; it prepares audio and captions
but does not produce a finished video or render QA report. `--preview-only`
still produces the review video, WAV stems, captions, contact sheet, manifest,
and QA report. `--size` changes dimensions only. `--overwrite` replaces known
generated outputs only in a directory recognized as a previous pilot render.
Keep source specifications, footage, fonts, and narration outside `--out`.

## What the pilot demonstrates

| Time | Scene | Demonstration |
| --- | --- | --- |
| 0–6 s | Title | Animated title, city background, local narration and word captions |
| 6–12 s | Route | Animated route map and incoming wipe |
| 12–18 s | Telemetry | Animated demonstration values and incoming dissolve |
| 18–24 s | Outro | Editable closing title, incoming wipe, synchronized audio finish |

All four scenes are exactly 180 frames. Transitions occupy the beginning of the
incoming scene, preserving the specified total duration. Demonstration routes
and values do not describe measured gameplay. The example contains no Rockstar
gameplay, logos, soundtrack recordings, or other downloaded media.

## Inputs and editing

Copy `examples/pilot.json` into your job directory and edit its data. The complete
contract is `schema.json`; additional, unknown fields are rejected.

| Field | Purpose |
| --- | --- |
| `project` | Title, demonstration flag, deterministic seed |
| `video` | Canvas, integer frame rate, total frame count |
| `style` | Palette, safe margin, caption placement, optional font files |
| `scenes` | Contiguous scene timing, text, background, route/metrics and transition |
| `narration` | Local synthetic lines or a local voice file and timestamp file |
| `captions` | Maximum words per cue, silence gap, line limit |
| `audio` | 48 kHz output, voice/music/effects gains, music tempo |

Titles, kickers, subtitles, scene durations, colors, typefaces, routes, metrics,
and narration are editable in JSON. Rerender to update the media. The clean
background and title/graphics layer remain separate in the Resolve export;
individual title glyphs and animation curves are rendered pixels. This pilot
does not create native Fusion Text+ nodes.

Scenes must cover the complete timeline with no gaps or overlaps. Times in
`start_frame`, `duration_frames`, and `transition_frames` are integer frames.
Word timestamps and narration offsets are seconds. Accepted frame rates are
24, 25, 30, 50, and 60; fractional/drop-frame rates are outside this version's
contract. Text is validated against layout limits; shorten or reflow failing
text rather than silently accepting clipping.

### Bring in gameplay or an image

Replace a scene's background with a local source. Paths are relative to the
specification file, or absolute local paths:

```json
{
  "kind": "video",
  "path": "assets/gameplay.mp4",
  "in_seconds": 12.5,
  "fit": "cover",
  "license": "User-provided recording; permission confirmed for this project",
  "credit": "Gameplay captured by the channel owner"
}
```

Use rights statements that are true for your asset; these example strings are
not a rights grant. `license` and `credit` are mandatory for supplied media.
`cover` crops to fill; `contain` preserves the full image with padding. Footage
audio is muted, and footage must contain enough frames after the in-point;
short sources fail instead of looping automatically. Use `kind: "image"` for
a still image and omit `in_seconds`. The renderer accepts local files only.

### Use narration and Deepgram timestamps

Replace the entire `narration` object with:

```json
{
  "mode": "file",
  "path": "assets/narration.wav",
  "captions_path": "assets/deepgram.json",
  "captions_format": "deepgram",
  "offset_seconds": 0,
  "channel": 0,
  "license": "User-owned narration",
  "credit": "Channel owner"
}
```

The Deepgram adapter reads
`results.channels[channel].alternatives[0].words`, using `punctuated_word` when
available. Supplied word times are preserved, with `offset_seconds` applied to
both narration audio and timestamps. No Deepgram API call occurs.
Shorter narration is padded with silence to the timeline length; narration that
extends beyond the timeline fails instead of being silently truncated.

The adapter also accepts a word array, `{"words": [...]}`, or
`{"segments": [{"words": [...]}]}` with entries such as:

```json
[
  {"word": "Read", "start": 0.31, "end": 0.56},
  {"word": "the", "start": 0.57, "end": 0.68},
  {"word": "route.", "start": 0.69, "end": 1.03}
]
```

Use `captions_format: "words"`, `"srt"`, or `"auto"` for those inputs. SRT and
segments without word timestamps estimate word positions within each phrase;
the timing source explicitly records this approximation. Existing cue text is
regrouped according to the configured caption rules. For precise word highlights,
supply actual word timestamps from the same narration recording. Overlapping,
negative, out-of-order, nonfinite, and out-of-timeline times are rejected.

The synthetic example speaks original demonstration text with the installed
Flite SLT voice. Word boundaries come from the same native synthesis result,
recorded as `flite-native-word-boundaries` in `audio-report.json`,
`manifest.json`, and `qa.json`. Synthetic voice quality is a functional stand-in
until you provide the desired narration.

### Claude integration

Use [CLAUDE-PROMPT.md](CLAUDE-PROMPT.md) as the starting task for Claude Code. It directs the agent
to read this template's `SKILL.md`, write schema-valid JSON, validate inputs,
render, and inspect outputs. The files and CLI are the integration boundary;
there is no embedded autonomous research agent, credential manager, or network
service in the renderer. Research claims and source selection belong in the job
brief before scene authoring. The pilot text makes no factual GTA news claims.

## Export files

| File | Format / role |
| --- | --- |
| `review.mp4` | H.264, 8-bit 4:2:0, Rec.709; mixed AAC stereo 48 kHz; titles and captions burned in |
| `resolve/clean.mov` | ProRes 422 HQ, 10-bit, Rec.709; full-duration background, no audio |
| `resolve/graphics.mov` | ProRes 4444 with straight alpha, Rec.709; titles/motion/transitions, no captions or audio |
| `resolve/narration.wav` | Full-duration 48 kHz stereo PCM16 voice stem |
| `resolve/music.wav` | Full-duration 48 kHz stereo PCM16 synthesized music stem |
| `resolve/sfx.wav` | Full-duration 48 kHz stereo PCM16 effects stem |
| `resolve/mix.wav` | Review mix; do not add alongside the individual stems |
| `timeline.xml` | Final Cut Pro 7 XML (`xmeml` v5) for a layered timeline |
| `captions.srt` | Separately editable subtitle cues with millisecond timestamps |
| `words.json` | Normalized timeline word timestamps |
| `resolved-spec.json` | Effective specification, including canvas overrides and resolved source paths |
| `audio-report.json` | Timing source, audio measurements and synchronization events |
| `qa.json` | Checks and measured output properties; read the actual status |
| `manifest.json` | Result status, inputs/source/output hashes, runtime versions and verification limits |
| `contact-sheet.jpg`, `frames/` | Representative frames extracted from the encoded review |

### Open the handoff in Resolve

1. Keep `timeline.xml`, `resolved-spec.json`, and `resolve/` together. If the
   export moved to another computer or folder, rebuild its absolute file URLs:

   ```bash
   python3 gta-production-pilot/handoff.py --out /path/to/export
   ```

   A delivery package may include its own `handoff.py`; from that package use
   `python3 handoff.py --out .`. This relocation command uses only Python's
   standard library and does not need the renderer, fonts, or original footage.

2. In a new Resolve project, use **File → Import → Timeline** and select
   `timeline.xml`. Match the specified canvas and frame rate, enable source
   media import, and retain the timeline start at **00:00:00:00**. If offered,
   enable importing multichannel audio as linked groups. Blackmagic documents
   the XML import controls in the
   [Resolve Colorist Guide, “Conforming an XML Timeline”](https://documents.blackmagicdesign.com/UserManuals/DaVinci-Resolve-20-Colorist-Guide.pdf).

3. Verify V1 is clean video and V2 is graphics using **Straight** alpha. Video
   clips are cut at scene boundaries and reference the full-duration masters.
   The three stereo stems are encoded as six linked mono channel tracks:
   narration L/R, music L/R, and SFX L/R. Check L/R routing and playback in your
   Resolve version before adjusting the mix. Do not also add `mix.wav`.

4. Import `captions.srt` into the Media Pool and place it on a subtitle track
   aligned to timeline zero. Check the first and last cues against the voice.
   Resolve provides editable subtitle tracks and styling controls; see
   [Blackmagic's subtitle documentation](https://www.blackmagicdesign.com/products/davinciresolve/edit).
   SRT preserves text and cue timing, not the animated word highlighting in
   `review.mp4`.

5. Compare with `review.mp4`, then edit, grade, mix, and finish. Changes to the
   template titles or animations require JSON changes and rerendering, or
   replacement with native Resolve titles.

**Resolve application import is not verified by this template's automated
checks.** The XML writer follows Apple's
[FCP7 element definitions](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/FinalCutPro_XML/Elements/Elements.html),
including frame timing, escaped local URLs, alpha type and stereo grouping.
Structural tests do not establish interoperability with a particular Resolve
version. If automatic conforming needs adjustment, the media can be assembled
manually at frame zero using the same V1/V2/stem arrangement.

## Verification

See [VERIFICATION.md](VERIFICATION.md) for the actual pilot renders, measured
export specifications, executed tests and remaining verification limits.

Run the focused tests from the repository root:

```bash
python3 -m unittest discover -s gta-production-pilot/tests -v
```

Every full or preview render measures encoded frame count, constant frame rate,
canvas, duration, color metadata, audio format and sample count, caption bounds,
and synchronization event positions. Full renders also check ProRes profiles
and actual transparent/opaque pixels in the graphics master. A failed check
sets `qa.json` and the manifest to `failed` and returns a nonzero exit status.

For a completed render, require a zero command exit status, `qa.json` with
`status: "passed"`, and `manifest.json` with `status: "passed"`. Inspect the
contact sheet, representative scene frames, each transition, and caption layout.
Listen to the review to judge intelligibility, music balance, and perceptual
caption synchronization. The automated checks establish technical properties;
they do not establish creative approval, publication readiness, or a successful
Resolve import. The manifest identifies the exact source and inputs used, so
do not describe an old render as verification of later source changes.

## Scope and boundaries

This first pilot implements a complete local sequence and a repeatable handoff.
It accepts local replacement footage and externally produced narration/timings.
Reference-video analysis, GTA research, full-length script generation, real
Deepgram calls, paid voice generation, native Resolve automation, and YouTube
publication are future integrations. The current renderer does not perform
those operations.

Keep the style provisional until the reference video is supplied. Obtain
explicit approval before paid generation calls, publishing, or merging changes.
Do not commit rendered media to this repository. Asset provenance and dependency
references are in `THIRD_PARTY_NOTICES.md`.
