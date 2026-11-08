"""Measured output checks and representative frames from the actual encoded render."""
from __future__ import annotations

import hashlib
import json
import math
import re
import wave
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from media import probe, run


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_frame(path: Path, seconds: float, out: Path) -> None:
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{seconds:.9f}", "-i", str(path),
         "-frames:v", "1", "-threads", "1", "-update", "1", str(out)])


def representative_frames(spec: dict, out: Path) -> list[dict]:
    fps = spec["video"]["fps"]
    frames = {0, spec["video"]["duration_frames"] - 1}
    for scene in spec["scenes"]:
        start = scene["start_frame"]
        frames.add(start + int(scene["duration_frames"] * .44))
        if start:
            frames.update([start - 1, start, start + max(0, scene["transition_frames"] // 2), start + scene["transition_frames"]])
    target = out / "frames"
    target.mkdir(exist_ok=True)
    results, thumbnails = [], []
    font = ImageFont.load_default(size=18)
    for frame in sorted(frames):
        name = f"frame-{frame:06d}.jpg"
        extract_frame(out / "review.mp4", frame / fps, target / name)
        with Image.open(target / name) as image:
            thumb = image.copy()
            thumb.thumbnail((480, 270))
        tile = Image.new("RGB", (480, 304), "#101722")
        tile.paste(thumb, ((480 - thumb.width) // 2, (270 - thumb.height) // 2))
        ImageDraw.Draw(tile).text((14, 279), f"FRAME {frame:03d}  /  {frame/fps:.3f}s", font=font, fill="#f4f2ed")
        thumbnails.append(tile)
        results.append({"frame": frame, "time_seconds": frame / fps, "path": f"frames/{name}"})
    cols = 4
    sheet = Image.new("RGB", (cols * 480, math.ceil(len(thumbnails) / cols) * 304), "#101722")
    for i, thumb in enumerate(thumbnails):
        sheet.paste(thumb, ((i % cols) * 480, (i // cols) * 304))
    sheet.save(out / "contact-sheet.jpg", quality=91)
    return results


def verify_outputs(spec: dict, out: Path, audio_meta: dict, preview_only: bool = False) -> dict:
    video = spec["video"]
    duration = video["duration_frames"] / video["fps"]
    checks, measurements = [], {}

    def check(name: str, passed: bool, actual=None):
        checks.append({"check": name, "passed": bool(passed), "actual": actual})

    videos = [("review.mp4", "h264")]
    if not preview_only:
        videos += [("resolve/clean.mov", "prores"), ("resolve/graphics.mov", "prores")]
    for name, codec in videos:
        data = probe(out / name, count_frames=True)
        stream = next(s for s in data["streams"] if s["codec_type"] == "video")
        measured = {k: stream.get(k) for k in ("codec_name", "profile", "width", "height", "pix_fmt", "r_frame_rate", "avg_frame_rate", "nb_read_frames", "duration", "color_space", "color_transfer", "color_primaries", "color_range")}
        measurements[name] = measured
        check(f"{name}: codec", stream["codec_name"] == codec, stream["codec_name"])
        check(f"{name}: dimensions", (stream["width"], stream["height"]) == (video["width"], video["height"]), [stream["width"], stream["height"]])
        check(f"{name}: constant frame rate", Fraction(stream["r_frame_rate"]) == video["fps"] and Fraction(stream["avg_frame_rate"]) == video["fps"], stream["avg_frame_rate"])
        check(f"{name}: decoded frame count", int(stream.get("nb_read_frames", -1)) == video["duration_frames"], stream.get("nb_read_frames"))
        check(f"{name}: duration", abs(float(stream["duration"]) - duration) <= 1 / video["fps"], stream["duration"])
        check(f"{name}: Rec.709 metadata", all(stream.get(k) == "bt709" for k in ("color_space", "color_transfer", "color_primaries")))
        if name == "review.mp4":
            aud = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
            check("review: AAC stereo at 48 kHz", aud and aud["codec_name"] == "aac" and aud["sample_rate"] == "48000" and aud["channels"] == 2)
            if aud:
                check("review: audio duration", abs(float(aud["duration"]) - duration) < .025, aud["duration"])
        elif name.endswith("clean.mov"):
            check("clean: 10-bit ProRes HQ", stream.get("pix_fmt") == "yuv422p10le" and stream.get("profile") == "HQ")
        else:
            check("graphics: ProRes 4444 alpha format", stream.get("profile") == "4444" and stream["pix_fmt"].startswith("yuva444"))
            raw = run(["ffmpeg", "-v", "error", "-ss", str(min(2, duration / 2)), "-i", str(out / name), "-vf", "alphaextract,format=gray", "-frames:v", "1", "-f", "rawvideo", "pipe:1"]).stdout
            alpha = np.frombuffer(raw, dtype=np.uint8)
            check("graphics: actual transparent and opaque pixels", len(alpha) > 0 and int(alpha.min()) == 0 and int(alpha.max()) == 255,
                  {"min": int(alpha.min()), "max": int(alpha.max()), "transparent_fraction": float(np.mean(alpha == 0))})

    for name in ("narration", "music", "sfx", "mix"):
        path = out / "resolve" / f"{name}.wav"
        with wave.open(str(path), "rb") as wav:
            channels, rate, frames, width = wav.getnchannels(), wav.getframerate(), wav.getnframes(), wav.getsampwidth()
            raw = wav.readframes(frames)
        check(f"{name}: PCM stereo 48 kHz", channels == 2 and rate == 48000 and width == 2, {"channels": channels, "rate": rate, "bits": 8 * width})
        expected = round(duration * rate)
        check(f"{name}: exact timeline sample count", frames == expected, frames)
        if width == 2:
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768
            peak = float(np.max(np.abs(samples)))
            rms = float(np.sqrt(np.mean(samples ** 2)))
            measurements[f"{name}.wav"] = {"samples": frames, "sample_peak": peak, "rms": rms}
            check(f"{name}: no PCM clipping", peak < 32767 / 32768, peak)
    # Measure the encoded soundtrack too: lossy AAC can peak above its PCM input.
    loudness_result = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(out / "review.mp4"), "-vn",
                           "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    blocks = re.findall(r'\{\s*"input_i".*?\}', loudness_result.stderr.decode(errors="replace"), re.DOTALL)
    if not blocks:
        raise RuntimeError("FFmpeg did not return encoded-audio loudness measurements")
    measured_loudness = json.loads(blocks[-1])
    measurements["encoded_audio"] = {"integrated_lufs": measured_loudness["input_i"],
                                      "true_peak_dbtp": measured_loudness["input_tp"],
                                      "loudness_range_lu": measured_loudness["input_lra"]}
    check("review: encoded true peak below 0 dBTP", float(measured_loudness["input_tp"]) < 0, measured_loudness["input_tp"])
    words = audio_meta["words"]
    check("captions: nonempty and inside timeline", bool(words) and all(0 <= w["start"] < w["end"] <= duration for w in words))
    check("captions: monotonic, nonoverlapping", all(a["end"] <= b["start"] + 1e-7 for a, b in zip(words, words[1:])))
    for event in audio_meta.get("sync_events", []):
        check(f"sync: {event.get('kind', 'event')} at frame {event['frame']}", event["sample"] == round(event["frame"] * 48000 / video["fps"]), event)
    report = {"status": "passed" if all(c["passed"] for c in checks) else "failed", "checks": checks, "measurements": measurements,
              "caption_timing_source": audio_meta.get("timing_source"),
              "limits": ["Automated checks do not replace a creative/audio review.", "DaVinci Resolve application import is not verified by this script.", "JSON titles re-render as graphics; no native Fusion title nodes are generated."]}
    (out / "qa.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
