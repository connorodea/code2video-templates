#!/usr/bin/env python3
"""Inspect an already-local reference video without sending it to a service.

Writes metadata, evenly spaced timestamped frames and a diagnostic contact sheet.
The output is evidence for an editorial review, not automatic semantic analysis.
Never commit reference media or frame captures to this repository.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw
from engine.style import font


def inspect(input_path: Path, output_dir: Path, samples: int) -> dict:
    if not input_path.is_file():
        raise ValueError(f"Not a local video file: {input_path}")
    for command in ("ffmpeg", "ffprobe"):
        if not shutil.which(command):
            raise RuntimeError(f"{command} must be installed and on PATH")
    if not 4 <= samples <= 60:
        raise ValueError("samples must be between 4 and 60")
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(input_path)
    ], capture_output=True, text=True, check=True, timeout=60)
    probe = json.loads(result.stdout)
    streams = [s for s in probe["streams"] if s["codec_type"] == "video"]
    if not streams:
        raise ValueError("Input has no video stream")
    video = streams[0]
    duration = float(probe["format"].get("duration") or video.get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Cannot determine a positive video duration")
    fps = Fraction(video.get("avg_frame_rate") or video["r_frame_rate"])
    if fps <= 0:
        raise ValueError("Cannot determine frame rate")
    output_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with input_path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    width, height = int(video["width"]), int(video["height"])
    thumb_w = 360
    thumb_h = round(thumb_w * height / width)
    cell_h = thumb_h + 30
    columns = min(4, samples)
    sheet = Image.new("RGB", (columns * thumb_w, math.ceil(samples / columns) * cell_h), "#181818")
    draw = ImageDraw.Draw(sheet)
    frame_records = []
    last = max(0, duration - 2 / float(fps))
    for index in range(samples):
        timestamp = last * index / (samples - 1)
        command = [
            "ffmpeg", "-v", "error", "-ss", f"{timestamp:.6f}", "-i", str(input_path),
            "-map", "0:v:0", "-frames:v", "1", "-vf", f"scale={thumb_w}:-1",
            "-f", "image2pipe", "-c:v", "png", "-threads", "1", "pipe:1"
        ]
        process = subprocess.run(command, capture_output=True, check=True, timeout=60)
        frame = Image.open(io.BytesIO(process.stdout)).convert("RGB")
        filename = f"frame-{index:02}-{timestamp:07.3f}.png"
        frame.save(output_dir / filename)
        x, y = (index % columns) * thumb_w, (index // columns) * cell_h
        sheet.paste(frame, (x, y))
        draw.text((x + 10, y + thumb_h + 6), f"{timestamp:06.3f}s", font=font(16, 600), fill="white")
        frame_records.append({"sample_index": index, "requested_time_seconds": round(timestamp, 6), "file": filename})
    sheet.save(output_dir / "contact-sheet.jpg", quality=90)
    metadata = {
        "input_filename": input_path.name,
        "input_sha256": digest.hexdigest(),
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "average_frame_rate": str(fps),
        "audio_streams": sum(s["codec_type"] == "audio" for s in probe["streams"]),
        "inspection_method": "uniform timestamp sampling; not a full playback or automatic shot-boundary analysis",
        "timing_note": "Requested timestamps may resolve to the next decodable frame; inspect exact cut boundaries separately.",
        "frames": frame_records,
        "contact_sheet": "contact-sheet.jpg",
    }
    (output_dir / "inspection.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=12)
    args = parser.parse_args()
    try:
        result = inspect(args.input.resolve(), args.out_dir.resolve(), args.samples)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Reference inspection failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
