#!/usr/bin/env python3
"""Render a validated Signature Motion config to an MP4 or a still image."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

from engine.validation import (
    ConfigError,
    canonical_json,
    config_hash,
    frame_count,
    load_config,
    local_file,
    preview_config,
)

ROOT = Path(__file__).resolve().parent
RENDERER_VERSION = "1.0.0"


class RenderError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def temporary_path(destination: Path, suffix: str) -> Path:
    handle, path = tempfile.mkstemp(prefix=f".{destination.stem}-", suffix=suffix, dir=destination.parent)
    os.close(handle)
    return Path(path)


def validate_images(config: dict) -> None:
    from PIL import Image
    for value in config["content"].get("assets", []):
        try:
            with Image.open(value) as image:
                image.verify()
        except (OSError, ValueError, SyntaxError) as exc:
            raise ConfigError(f"content.assets: cannot decode image {value}: {exc}") from exc


def checked_frame(config: dict, index: int):
    from engine.scenes import render_frame
    image = render_frame(config, index)
    if image.size != (config["width"], config["height"]):
        raise RenderError(f"Frame {index} has size {image.size}; expected {(config['width'], config['height'])}.")
    return image.convert("RGB")


def manifest_for(raw: dict, config: dict, source: Path, audio: Path | None, output: Path, mode: str, index: int | None) -> dict:
    from engine.style import font_path
    from PIL import features
    assets = [Path(item) for item in config["content"].get("assets", [])]
    fonts = list(dict.fromkeys([Path(font_path(False)), Path(font_path(True))]))
    asset_hashes = [{"path": str(path), "sha256": sha256_file(path)} for path in assets]
    font_hashes = [{"name": path.name, "sha256": sha256_file(path)} for path in fonts]
    code_hashes = {
        str(path.relative_to(ROOT)): sha256_file(path)
        for path in sorted([ROOT / "render.py", *ROOT.glob("engine/*.py")])
    }
    libraries = {}
    for package in ("Pillow",):
        try:
            libraries[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            libraries[package] = "unavailable"
    runtime = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "freetype": features.version("freetype2"),
    }
    if mode == "video":
        executable = shutil.which("ffmpeg")
        if executable is None:
            raise RenderError("FFmpeg is required for MP4 export; install it and place it on PATH.")
        version = subprocess.run([executable, "-version"], capture_output=True, text=True, check=True, timeout=10)
        runtime["ffmpeg"] = version.stdout.splitlines()[0]
        runtime["ffmpeg_build_sha256"] = hashlib.sha256(version.stdout.encode()).hexdigest()
    audio_info = None if audio is None else {"path": str(audio), "sha256": sha256_file(audio)}
    fingerprint_input = {
        "config": raw,
        "width": config["width"],
        "height": config["height"],
        "assets": [entry["sha256"] for entry in asset_hashes],
        "fonts": font_hashes,
        "audio": None if audio_info is None else audio_info["sha256"],
        "renderer_version": RENDERER_VERSION,
        "renderer_files": code_hashes,
        "libraries": libraries,
        "runtime": runtime,
        "mode": mode,
        "still_frame": index,
    }
    return {
        "schema_version": 1,
        "renderer_version": RENDERER_VERSION,
        "template": config["template"],
        "demo": config["demo"],
        "config_path": str(source),
        "requested_dimensions": {"width": raw["width"], "height": raw["height"]},
        "config_sha256": config_hash(raw),
        "render_fingerprint": hashlib.sha256(canonical_json(fingerprint_input).encode("utf-8")).hexdigest(),
        "width": config["width"],
        "height": config["height"],
        "fps": config["fps"],
        "duration": config["duration"],
        "frame_count": frame_count(config),
        "mode": mode,
        "still_frame": index,
        "output": str(output),
        "assets": asset_hashes,
        "audio": audio_info,
        "fonts": font_hashes,
        "libraries": libraries,
        "runtime": runtime,
        "renderer_files": code_hashes,
    }


def render_video(config: dict, temporary: Path, audio: Path | None) -> None:
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise RenderError("FFmpeg is required for MP4 export; install it and place it on PATH.")
    command = [
        executable, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-video_size", f"{config['width']}x{config['height']}",
        "-framerate", str(config["fps"]), "-i", "pipe:0",
    ]
    if audio is not None:
        command += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-af", "apad", "-c:a", "aac", "-b:a", "192k"]
    else:
        command += ["-an"]
    command += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-threads", "2",
        "-pix_fmt", "yuv420p", "-frames:v", str(frame_count(config)),
        "-t", str(config["duration"]), "-movflags", "+faststart", str(temporary),
    ]
    with tempfile.TemporaryFile(mode="w+b") as error_log:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=error_log)
        try:
            assert process.stdin is not None
            for index in range(frame_count(config)):
                image = checked_frame(config, index)
                process.stdin.write(image.tobytes())
            process.stdin.close()
            returncode = process.wait(timeout=120)
        except BaseException as exc:
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            error_log.seek(0)
            detail = error_log.read().decode("utf-8", errors="replace").strip()
            if isinstance(exc, (BrokenPipeError, subprocess.TimeoutExpired)):
                raise RenderError(f"FFmpeg export failed: {detail or str(exc)}") from exc
            raise
        error_log.seek(0)
        detail = error_log.read().decode("utf-8", errors="replace").strip()
    if returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
        raise RenderError(f"FFmpeg export failed (exit {returncode}): {detail}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--list", action="store_true", help="Print the template registry as JSON.")
    action.add_argument("--validate", action="store_true", help="Validate a config without importing drawing libraries.")
    action.add_argument("--out", type=Path, help="Write an H.264 MP4.")
    action.add_argument("--still", type=Path, help="Write one PNG frame.")
    parser.add_argument("--config", type=Path, help="Input JSON config; assets resolve relative to this file.")
    parser.add_argument("--time", type=float, help="Still timestamp in seconds; defaults to the midpoint.")
    parser.add_argument("--preview", type=float, default=1.0, metavar="SCALE", help="Scale dimensions to (0,1], retaining exact aspect and even dimensions.")
    parser.add_argument("--audio", type=str, help="One local audio track, relative to the config file; pad or trim to video length.")
    args = parser.parse_args()
    if not args.list and args.config is None:
        parser.error("--config is required unless --list is used")
    if args.time is not None and args.still is None:
        parser.error("--time requires --still")
    if args.audio is not None and args.out is None:
        parser.error("--audio requires --out")
    return args


def main() -> int:
    args = parse_args()
    temporary = None
    temporary_manifest = None
    try:
        if args.list:
            print((ROOT / "templates.json").read_text(encoding="utf-8"))
            return 0
        source = args.config.expanduser().resolve()
        raw, config = load_config(source)
        config = preview_config(config, args.preview)
        description = {
            "valid": True, "template": config["template"], "width": config["width"],
            "height": config["height"], "fps": config["fps"], "duration": config["duration"],
            "frame_count": frame_count(config), "config_sha256": config_hash(raw),
            "assets": config["content"].get("assets", []),
        }
        if args.validate:
            print(json.dumps(description, indent=2))
            return 0
        audio = None if args.audio is None else local_file(args.audio, source.parent, "audio")
        output = (args.out if args.out is not None else args.still).expanduser().resolve()
        mode = "video" if args.out is not None else "still"
        expected_suffix = ".mp4" if mode == "video" else ".png"
        if output.suffix.lower() != expected_suffix:
            raise ConfigError(f"Output must end in {expected_suffix}.")
        inputs = {source, *[Path(item) for item in config["content"].get("assets", [])]}
        if audio is not None:
            inputs.add(audio)
        manifest_path = output.with_name(output.name + ".manifest.json")
        if output in inputs or manifest_path in inputs:
            raise ConfigError("Output and manifest paths must differ from all input paths.")
        validate_images(config)
        index = None
        if mode == "still":
            timestamp = config["duration"] / 2 if args.time is None else args.time
            if not math.isfinite(timestamp) or not 0 <= timestamp < config["duration"]:
                raise ConfigError("--time must be finite and within [0, duration).")
            index = min(frame_count(config) - 1, math.floor(timestamp * config["fps"]))
        manifest = manifest_for(raw, config, source, audio, output, mode, index)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = temporary_path(output, expected_suffix)
        if mode == "video":
            render_video(config, temporary, audio)
        else:
            checked_frame(config, index).save(temporary, format="PNG")
        manifest["output_sha256"] = sha256_file(temporary)
        manifest["output_bytes"] = temporary.stat().st_size
        temporary_manifest = temporary_path(manifest_path, ".json")
        temporary_manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temporary, output)
        temporary = None
        os.replace(temporary_manifest, manifest_path)
        temporary_manifest = None
        print(json.dumps({**description, "output": str(output), "manifest": str(manifest_path), "mode": mode}, indent=2))
        return 0
    except (ConfigError, RenderError, OSError, ImportError, subprocess.SubprocessError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}), file=sys.stderr)
        return 1
    finally:
        for item in (temporary, temporary_manifest):
            if item is not None:
                item.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
