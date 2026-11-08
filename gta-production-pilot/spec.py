"""Strict, local-only scene contract shared by CLI and agent integrations."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent


def local_path(value: str, base: Path) -> Path:
    if "://" in value or value.startswith(("data:", "pipe:", "concat:", "file:")):
        raise ValueError(f"Expected an existing local file, not a URL: {value!r}")
    path = Path(value).expanduser()
    path = (base / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_file():
        raise ValueError(f"Local file does not exist: {path}")
    return path


def _finite(value: Any, location: str = "spec") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{location}: numeric values must be finite")
    if isinstance(value, dict):
        for key, item in value.items():
            _finite(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _finite(item, f"{location}[{index}]")


def validate_spec(spec: dict, base: Path, check_files: bool = True) -> None:
    _finite(spec)
    schema = json.loads((HERE / "schema.json").read_text())
    errors = sorted(Draft202012Validator(schema).iter_errors(spec), key=lambda e: str(list(e.path)))
    if errors:
        message = "\n".join(f"{'.'.join(map(str, e.path)) or 'spec'}: {e.message}" for e in errors[:8])
        raise ValueError(message)
    video = spec["video"]
    if video["width"] * video["height"] > 3840 * 2160:
        raise ValueError("Canvas area must not exceed 3840 x 2160 pixels")
    if video["duration_frames"] / video["fps"] > 600:
        raise ValueError("Pilot renderer supports at most 10 minutes per job")
    cursor, ids = 0, set()
    for scene in spec["scenes"]:
        if scene["id"] in ids:
            raise ValueError(f"Duplicate scene id: {scene['id']}")
        ids.add(scene["id"])
        if scene["start_frame"] != cursor:
            raise ValueError(f"Scene {scene['id']} must start at frame {cursor}; gaps and overlaps are not allowed")
        if scene["transition_frames"] > scene["duration_frames"] // 2:
            raise ValueError(f"Scene {scene['id']}: transition must fit within half its duration")
        if scene["transition_in"] == "cut" and scene["transition_frames"] != 0:
            raise ValueError(f"Scene {scene['id']}: a cut must have zero transition frames")
        if scene["transition_in"] != "cut" and scene["transition_frames"] == 0:
            raise ValueError(f"Scene {scene['id']}: animated transitions need at least one frame")
        if cursor == 0 and scene["transition_in"] != "cut":
            raise ValueError("The first scene must use a cut")
        if scene["kind"] == "route" and "route" not in scene:
            raise ValueError(f"Scene {scene['id']}: route points are required")
        if scene["kind"] == "telemetry" and "metrics" not in scene:
            raise ValueError(f"Scene {scene['id']}: telemetry metrics are required")
        background = scene["background"]
        if check_files and background["kind"] != "synthetic":
            local_path(background["path"], base)
        if background["kind"] == "image" and background.get("in_seconds", 0):
            raise ValueError("An image background cannot have a source in-point")
        cursor += scene["duration_frames"]
    if cursor != video["duration_frames"]:
        raise ValueError(f"Scenes cover {cursor} frames, but video.duration_frames is {video['duration_frames']}")
    narration = spec["narration"]
    if narration["mode"] == "synthetic":
        if not spec["project"]["demo"]:
            raise ValueError("Synthetic narration is a demonstration mode: project.demo must be true")
        starts = [line["start_frame"] for line in narration["lines"]]
        if starts != sorted(set(starts)) or starts[-1] >= cursor:
            raise ValueError("Narration starts must be unique, increasing, and inside the timeline")
    elif check_files:
        local_path(narration["path"], base)
        local_path(narration["captions_path"], base)
    for key in ("font_regular", "font_bold"):
        if check_files and key in spec["style"]:
            local_path(spec["style"][key], base)


def load_spec(path: Path) -> dict:
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read scene specification: {exc}") from exc
    validate_spec(spec, path.resolve().parent)
    return spec
