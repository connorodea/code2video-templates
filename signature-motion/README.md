# Signature Motion

Six reusable video templates with distinct visual identities, a strict JSON input contract, and a local Python → FFmpeg renderer. Use them as individual scenes inside an agent-directed edit, or as standalone short videos.

| Template | Signature motion | Best use |
|---|---|---|
| **Type Impact** | Large editorial words rise through masks, resolve into a statement, and close on a CTA | Hooks, positioning, launch announcements |
| **Redline** | An excerpt arrives on textured paper; a moving highlight guides attention to a conclusion | Research, evidence, explainers |
| **Signal** | A proportional line chart draws through supplied observations and resolves on the final value | Analytics, trend stories, research findings |
| **Flow State** | Scattered task strips reorganize into an ordered sequence | Workflows, automation, product explanations |
| **Prism** | Dimensional panels arrange into a deliberate media composition | Screenshots, portfolios, product details |
| **After Hours** | An iris of geometric arcs opens around oversized title typography | Openers, event titles, branded bumpers |

These are implemented starter templates. [REVERSE-ENGINEERING.md](REVERSE-ENGINEERING.md) breaks down seven real video references into reusable editing mechanisms. [motion-recipes.json](motion-recipes.json) gives agents their proposed inputs, beats and evaluation checks; these advanced recipes are design-only. [CONCEPTS.md](CONCEPTS.md) adds twelve further directions with storyboards and required inputs.

## Run

Requires Python 3.10+, FFmpeg on PATH, and the local dependencies in `requirements.txt`. The renderer reuses the repository's OFL-licensed Inter font. It makes no network calls and uses no generation credits.

From this folder:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python render.py --list
.venv/bin/python render.py --config examples/type-impact.json --validate
.venv/bin/python render.py --config examples/type-impact.json --out out/type-impact.mp4
```

Or use the one-command wrapper after installing the dependencies in your active Python environment:

```bash
bash make.command
```

The six example JSON files are editable. All examples visibly identify themselves as demos. Their copy and numeric series are illustrative, not measurements or claims about a customer, channel, or product.

### Preview and audio

```bash
python3 render.py --config examples/redline.json --still out/redline.png --time 5
python3 render.py --config examples/signal.json --out out/signal.mp4
python3 render.py --config examples/prism.json --preview 0.5 --out out/prism-preview.mp4
python3 render.py --config examples/type-impact.json --out out/with-audio.mp4 --audio /absolute/path/approved-audio.wav
```

`--preview 0.5` halves the dimensions, rounded to an even exact aspect ratio; the shorter edge stays at least 144 pixels. By default the output is silent, ready for the parent editor's voiceover, music and captions. Optional audio is one supplied track; this package does not synthesize speech, detect beats, time-stretch dialogue, or mix multiple tracks.

Media outputs remain in ignored `out/` directories. No rendered video, image, or audio is committed. A hosted public preview is not bundled; the commands above reproduce the examples locally.

## Agent integration

Use [templates.json](templates.json) for discovery and [schema.json](schema.json) for structured output. Validate a complete request before allocating a render worker. Read [INTEGRATION.md](INTEGRATION.md) for the suggested orchestration contract, evidence handling, cache identity and production boundaries.

The JSON Schema checks structure and field limits. The CLI validator additionally checks exact aspect ratios, whole-frame durations, source URL semantics, and local asset paths; always run it before rendering.

The renderer writes an adjacent JSON result with reproducibility information. Use the actual returned output dimensions, duration and frame count when placing the clip on the parent timeline. Full-frame H.264 MP4 is the supported compositing format; transparent overlays, video-backed panels, and native editor projects are future work.

The supported shapes are portrait 9:16, landscape 16:9 and square 1:1. Each scene adapts its layout. This is not a guarantee against every social platform's changing UI overlays; inspect the final assembled video in its target format.

### Direct frame access

The public frame function is suitable for a Python render worker:

```python
from engine.scenes import render_frame

# Validate the complete config with the CLI/validator first.
image = render_frame(validated_config, frame_index=90)
```

Frames use half-open bounds: `0 <= frame_index < duration * fps`. Scene state is calculated from the requested frame, so seeks and parallel frame evaluation do not depend on prior frames. Identical output also requires identical font bytes, Pillow/FreeType versions and encoder settings; input JSON alone is not a cross-machine reproducibility guarantee.

## Verification

For a local reference video, produce metadata and timestamped frames for editorial review:

```bash
python3 inspect_reference.py /absolute/path/reference.mp4 --out-dir out/reference-study --samples 12
```

This utility samples frames; it does not detect every cut, analyze sound, or establish why a video performed well. Keep reference media and captured frames out of Git. [references.json](references.json) records the sources, dated reach evidence and inspection limits used for this pack.

Run contract and frame checks:

```bash
python3 -m unittest discover -s tests -v
```

This checks meaningful contract and frame behavior. Render representative frames and inspect the resulting MP4 before use. The examples are not an exhaustive test of every language, font, input length or operating system.

## License

Code follows the repository MIT license. Inter remains under its existing OFL notice at `../apple-notes-video/vendor/assets/InterVariable-OFL.txt`. Set `SIGNATURE_MOTION_FONT` to a local font file if required, and retain that font's own license. Supplied images and audio retain their owners' rights.
