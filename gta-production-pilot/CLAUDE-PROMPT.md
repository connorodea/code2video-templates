# Claude production task

Use this prompt with Claude Code in this repository. It controls the local pilot
through structured files; the template itself makes no LLM, Deepgram, or other
network calls.

```text
Build one GTA production pilot from my brief using gta-production-pilot.

Read AGENTS.md, gta-production-pilot/SKILL.md, schema.json and examples/pilot.json.
Create a separate job directory and a scene-spec.json that satisfies the schema.
Use integer frames for scenes and seconds for word timestamps. Keep all scenes
contiguous. Transitions consume the first frames of the incoming scene.

Use the bundled synthetic assets until I provide authorized local footage and a
reference video. Treat all styling, titles, palette and layout as configurable
draft choices. Preserve project.demo=true for demonstrations. Mark synthetic
figures as demonstrations; do not present them as measured gameplay facts.

For real narration, use narration.mode=file. Point path to the local voice file
and captions_path to its Deepgram prerecorded JSON, normalized timed words, or
SRT. Caption the exact speech. Apply offset_seconds equally to audio and word
timestamps. SRT supports phrase timing; its within-cue word timing is estimated.
Set license and credit fields for each supplied media file. Do not invent rights.
If media, timing or rights information is missing, use the synthetic pilot or
identify the precise missing input; do not download replacement gameplay.

Validate the spec. Render a still and inspect it, then launch the full render in
a background terminal job with a log. Keep the job's source files outside --out.
Do not edit the engine to make routine content changes.

Require a zero exit status, manifest.json status=passed and qa.json status=passed.
Inspect representative encoded frames, especially every transition and caption
layout. Review audio intelligibility and caption synchronization when playback
is available; distinguish measured timing checks from human playback review.
For Resolve, use clean.mov on V1, graphics.mov on V2 with straight alpha, separate
voice/music/SFX stems, and captions.srt. Titles remain editable in scene JSON;
the exported graphics are not native Fusion text nodes.

Return the exact render paths, duration, dimensions, frame rate, timing source,
validation results and any remaining application-import or creative-review gaps.
Never call paid generation services, publish a video, or merge code without
showing me the specific proposed action and obtaining explicit approval.
```

## Job commands

From the repository root, after creating `jobs/example/scene-spec.json`:

```bash
python3 gta-production-pilot/render.py --spec jobs/example/scene-spec.json --validate
python3 gta-production-pilot/render.py --spec jobs/example/scene-spec.json --out jobs/example/still --still 2.4
python3 gta-production-pilot/render.py --spec jobs/example/scene-spec.json --out jobs/example/render
```

Use a unique output directory per job or explicitly use `--overwrite` for an
existing renderer output. The bundled `make.command` runs the complete default
example without any API key or generation credits.
