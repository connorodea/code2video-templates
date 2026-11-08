#!/usr/bin/env python3
"""Render a structured GTA production pilot entirely with local tools."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from audio import prepare_audio
from captions import chunk_words, write_srt
from handoff import write_handoff
from media import BackgroundSource, Encoder, check_sources, run
from qa import representative_frames, sha256, verify_outputs
from spec import HERE, load_spec, local_path, validate_spec
from visuals import FrameRenderer


def output_directory(path: Path, overwrite: bool) -> Path:
    out = path.resolve()
    marker = out / ".gta-pilot-output"
    if out.exists() and any(out.iterdir()):
        if not overwrite:
            raise ValueError(f"Output directory is not empty: {out}. Choose another --out or use --overwrite.")
        if not marker.is_file():
            raise ValueError("--overwrite only works in a directory created by this renderer")
    out.mkdir(parents=True, exist_ok=True)
    marker.write_text("gta-production-pilot v1\n")
    (out / "resolve").mkdir(exist_ok=True)
    # Remove only our named outputs, so a new preview/still cannot inherit a stale
    # full-render manifest or media. Never recursively delete a user directory.
    generated = ["manifest.json", "qa.json", "review.mp4", "_review-silent.mp4", "timeline.xml",
                 "resolved-spec.json", "audio-report.json", "words.json", "captions.srt", "contact-sheet.jpg", "still.jpg",
                 "handoff.py", "OPEN-IN-RESOLVE.md"]
    generated += [f"resolve/{name}" for name in ("clean.mov", "graphics.mov", "narration.wav", "music.wav", "sfx.wav", "mix.wav")]
    for name in generated:
        (out / name).unlink(missing_ok=True)
    for frame in (out / "frames").glob("frame-*.jpg"):
        frame.unlink()
    return out


def resolved_spec(spec: dict, base: Path) -> dict:
    copied = json.loads(json.dumps(spec))
    for scene in copied["scenes"]:
        if "path" in scene["background"]:
            scene["background"]["path"] = str(local_path(scene["background"]["path"], base))
    for key in ("path", "captions_path"):
        if key in copied["narration"]:
            copied["narration"][key] = str(local_path(copied["narration"][key], base))
    for key in ("font_regular", "font_bold"):
        if key in copied["style"]:
            copied["style"][key] = str(local_path(copied["style"][key], base))
    return copied


def render(spec: dict, spec_path: Path, out: Path, preview_only: bool = False, still: float | None = None) -> dict:
    started = time.monotonic()
    video, base = spec["video"], spec_path.parent
    duration = video["duration_frames"] / video["fps"]
    renderer = FrameRenderer(spec, base)
    sources = check_sources(spec, base)
    print("Preparing local narration, word timings, music and effects…", flush=True)
    audio = prepare_audio(spec, base, out)
    words = audio["words"]
    warnings = renderer.validate_layout(words)
    chunks = chunk_words(words, max_words=spec["captions"]["max_words"], gap_seconds=spec["captions"]["gap_seconds"])
    write_srt(chunks, out / "captions.srt")
    (out / "words.json").write_text(json.dumps(words, indent=2) + "\n")
    (out / "resolved-spec.json").write_text(json.dumps(resolved_spec(spec, base), indent=2) + "\n")
    (out / "audio-report.json").write_text(json.dumps(audio, indent=2) + "\n")
    source = BackgroundSource(spec, base, renderer)
    if still is not None:
        if not 0 <= still < duration:
            raise ValueError(f"--still must be between 0 and {duration:g} seconds (exclusive)")
        frame = int(still * video["fps"])
        # Sequentially consume earlier frames of this scene when it uses real footage.
        scene = next(s for s in spec["scenes"] if s["start_frame"] <= frame < s["start_frame"] + s["duration_frames"])
        for i in range(scene["start_frame"], frame + 1):
            background = source.frame(i)
        review = Image.alpha_composite(background.convert("RGBA"), renderer.render_graphics(frame, words, include_captions=True)).convert("RGB")
        review.save(out / "still.jpg", quality=95)
        # A still intentionally leaves a source partially consumed: terminate its decoder.
        if source.decoder:
            source.decoder.kill()
            source.decoder.wait()
            source.decoder = None
        source.close()
        return {"status": "still_only", "file": str(out / "still.jpg"), "frame": frame}
    encoders = []
    try:
        review_encoder = Encoder(out / "_review-silent.mp4", video, "review")
        encoders.append(review_encoder)
        if not preview_only:
            clean_encoder = Encoder(out / "resolve" / "clean.mov", video, "clean")
            graphics_encoder = Encoder(out / "resolve" / "graphics.mov", video, "graphics")
            encoders.extend([clean_encoder, graphics_encoder])
        print(f"Rendering {video['duration_frames']} frames at {video['width']}x{video['height']} / {video['fps']} fps (PID {os.getpid()})…", flush=True)
        for frame in range(video["duration_frames"]):
            background = source.frame(frame)
            graphics = renderer.render_graphics(frame, words, include_captions=True)
            review_encoder.write(Image.alpha_composite(background.convert("RGBA"), graphics).convert("RGB"))
            if not preview_only:
                clean_encoder.write(background)
                graphics_encoder.write(renderer.render_graphics(frame, words, include_captions=False))
            if frame % (video["fps"] * 3) == 0:
                print(f"  {frame:4d}/{video['duration_frames']} frames ({time.monotonic()-started:.1f}s elapsed)", flush=True)
        source.close()
        for encoder in encoders:
            encoder.close()
    except BaseException:
        for encoder in encoders:
            encoder.abort()
        if source.decoder:
            source.decoder.kill()
            source.decoder.wait()
        raise
    run(["ffmpeg", "-v", "error", "-y", "-i", str(out / "_review-silent.mp4"), "-i", str(out / "resolve" / "mix.wav"),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
         "-t", f"{duration:.9f}", "-movflags", "+faststart", str(out / "review.mp4")])
    (out / "_review-silent.mp4").unlink()
    if not preview_only:
        write_handoff(spec, out)
        shutil.copyfile(HERE / "handoff.py", out / "handoff.py")
        (out / "OPEN-IN-RESOLVE.md").write_text(
            f"# GTA pilot edit handoff\n\n{video['width']} x {video['height']}, {video['fps']} fps, {duration:g} seconds.\n\n"
            "After moving or extracting this folder, run `python3 handoff.py --out .` from this folder. "
            "This updates timeline.xml to the media's current absolute paths; it uses only Python's standard library.\n\n"
            "Import timeline.xml into Resolve and verify that all media is online. Import captions.srt separately "
            "onto a subtitle track. V1 is clean.mov; V2 is graphics.mov (straight alpha). Audio consists of "
            "three independent stereo stems represented in XML as linked left/right channel pairs. "
            "Do not add mix.wav on top of these stems; it is an alternative premix.\n\n"
            "The graphics master has titles and motion but no burned captions. Change title text, colors, "
            "scene timing, graphics or font through the repository's scene JSON and re-render. The graphics "
            "are raster layers, not native Fusion title generators. review.mp4 is a captioned reference.\n\n"
            "If XML import differs in your Resolve version, import clean.mov, graphics.mov and the WAV stems "
            "manually and align them all at 00:00:00:00 in a timeline with the frame rate above. Add the SRT "
            "as subtitles. Inspect alpha interpretation and audio channel routing.\n\n"
            "The files and timing were checked with FFmpeg; actual Resolve application import remains "
            "unverified until you open the project.\n", encoding="utf-8")
    print("Checking encoded frames, audio sample counts, alpha and timeline timing…", flush=True)
    report = verify_outputs(spec, out, audio, preview_only)
    frames = representative_frames(spec, out)
    inputs = [{"role": "scene_spec", "path": str(spec_path), "sha256": sha256(spec_path)}]
    for record in sources:
        inputs.append({**record, "sha256": sha256(Path(record["path"]))})
    if spec["narration"]["mode"] == "file":
        for key in ("path", "captions_path"):
            path = local_path(spec["narration"][key], base)
            inputs.append({"role": key, "path": str(path), "sha256": sha256(path)})
    manifest = {
        "status": report["status"], "created_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.monotonic() - started, 2), "preview_only": preview_only,
        "video": video, "project": spec["project"], "paid_generation_calls": 0,
        "caption_timing_source": audio["timing_source"], "warnings": warnings,
        "inputs": inputs,
        "source_files": {p.name: sha256(p) for p in sorted(HERE.glob("*.py"))},
        "fonts": {role: {"path": str(path), "sha256": sha256(Path(path))} for role, path in getattr(renderer, "font_paths", {}).items()},
        "runtime": {"python": sys.version.split()[0], **{name: importlib.metadata.version(name) for name in ("Pillow", "numpy", "jsonschema")},
                    "ffmpeg": run(["ffmpeg", "-version"]).stdout.decode().splitlines()[0]},
        "representative_frames": frames,
        "outputs": [{"path": str(path.relative_to(out)), "bytes": path.stat().st_size, "sha256": sha256(path)}
                    for path in sorted(out.rglob("*")) if path.is_file() and path.suffix not in (".log",) and not path.name.startswith(".")],
        "resolve_import": "not_application_verified",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if report["status"] != "passed":
        failed = [check["check"] for check in report["checks"] if not check["passed"]]
        raise RuntimeError("Render completed but QA failed: " + "; ".join(failed))
    return {"status": "passed", "video": str(out / "review.mp4"), "frames": video["duration_frames"], "duration_seconds": duration,
            "elapsed_seconds": manifest["elapsed_seconds"], "qa": str(out / "qa.json"), "preview_only": preview_only}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=HERE / "examples" / "pilot.json")
    parser.add_argument("--out", type=Path, default=HERE / "out" / "pilot")
    parser.add_argument("--validate", action="store_true", help="Validate JSON, layout and source media without rendering")
    parser.add_argument("--preview-only", action="store_true", help="Skip ProRes and XML; still render review, captions and audio")
    parser.add_argument("--size", help="Override canvas dimensions, e.g. 960x540, keeping timing unchanged")
    parser.add_argument("--still", type=float, metavar="SECONDS", help="Render one composited still, with actual timed captions")
    parser.add_argument("--overwrite", action="store_true", help="Replace known outputs in a previous pilot output directory")
    args = parser.parse_args(argv)
    try:
        for binary in ("ffmpeg", "ffprobe"):
            if not shutil.which(binary):
                raise ValueError(f"{binary} is required; install FFmpeg before rendering")
        path = args.spec.resolve()
        spec = load_spec(path)
        if args.size:
            try:
                spec["video"]["width"], spec["video"]["height"] = map(int, args.size.lower().split("x"))
            except ValueError as exc:
                raise ValueError("--size must be WIDTHxHEIGHT, for example 960x540") from exc
            validate_spec(spec, path.parent)
        check_sources(spec, path.parent)
        if args.validate:
            renderer = FrameRenderer(spec, path.parent)
            renderer.validate_layout([])
            print(json.dumps({"status": "valid", "frames": spec["video"]["duration_frames"], "video": spec["video"]}))
            return 0
        input_paths = [path]
        input_paths += [local_path(s["background"]["path"], path.parent) for s in spec["scenes"] if "path" in s["background"]]
        input_paths += [local_path(spec["narration"][key], path.parent) for key in ("path", "captions_path") if key in spec["narration"]]
        input_paths += [local_path(spec["style"][key], path.parent) for key in ("font_regular", "font_bold") if key in spec["style"]]
        if any(p.is_relative_to(args.out.resolve()) for p in input_paths):
            raise ValueError("Keep input files outside --out; choose a separate output directory")
        out = output_directory(args.out, args.overwrite)
        print(json.dumps(render(spec, path, out, args.preview_only, args.still), indent=2))
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Render failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
