"""Local media IO. No shell, network fetches, or service credentials."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

from spec import local_path


def run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"{argv[0]} failed ({result.returncode}): {detail}")
    return result


def probe(path: Path, count_frames: bool = False) -> dict:
    argv = ["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe"]
    if count_frames:
        argv.append("-count_frames")
    argv += ["-show_streams", "-show_format", "-of", "json", str(path)]
    return json.loads(run(argv).stdout)


def check_sources(spec: dict, base: Path) -> list[dict]:
    records = []
    for scene in spec["scenes"]:
        bg = scene["background"]
        if bg["kind"] == "synthetic":
            continue
        path = local_path(bg["path"], base)
        if bg["kind"] == "image":
            with Image.open(path) as image:
                image.verify()
            records.append({"scene": scene["id"], "path": str(path), "kind": "image"})
            continue
        data = probe(path)
        stream = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
        if stream is None:
            raise ValueError(f"Scene {scene['id']}: no video stream in {path}")
        source_duration = float(stream.get("duration", data["format"].get("duration", 0)))
        required_end = bg.get("in_seconds", 0) + scene["duration_frames"] / spec["video"]["fps"]
        if source_duration + 1e-6 < required_end:
            raise ValueError(f"Scene {scene['id']}: footage needs {required_end:.3f}s, has {source_duration:.3f}s; no automatic looping")
        records.append({"scene": scene["id"], "path": str(path), "kind": "video", "source_duration": source_duration})
    return records


class BackgroundSource:
    """Stream each source once; normalize its frame rate before frame-indexed compositing."""

    def __init__(self, spec: dict, base: Path, renderer):
        self.spec, self.base, self.renderer = spec, base, renderer
        self.scene_id = None
        self.decoder = None
        self.decoder_log = None
        self.image = None
        self.size = (spec["video"]["width"], spec["video"]["height"])

    def close(self):
        if self.decoder:
            if self.decoder.stdout:
                self.decoder.stdout.close()
            try:
                result = self.decoder.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.decoder.kill()
                self.decoder.wait()
                result = -1
            self.decoder = None
            if result:
                message = self.decoder_log.read().decode(errors="replace") if self.decoder_log else ""
                raise RuntimeError(f"Background decoder failed: {message[-2000:]}")

    def _begin(self, scene: dict):
        self.close()
        self.scene_id = scene["id"]
        bg = scene["background"]
        self.image = None
        if bg["kind"] == "synthetic":
            return
        path = local_path(bg["path"], self.base)
        cover = bg.get("fit", "cover") == "cover"
        if bg["kind"] == "image":
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                self.image = ImageOps.fit(image, self.size) if cover else ImageOps.pad(image, self.size, color=self.spec["style"]["background"])
            return
        w, h = self.size
        fit = f"scale={w}:{h}:force_original_aspect_ratio={'increase' if cover else 'decrease'}"
        fit += f",crop={w}:{h}" if cover else f",pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x{self.spec['style']['background'][1:]}"
        fit += f",setsar=1,fps={self.spec['video']['fps']},format=rgb24"
        self.decoder = subprocess.Popen([
            "ffmpeg", "-v", "error", "-threads", "2", "-filter_threads", "1", "-protocol_whitelist", "file,pipe",
            "-ss", str(bg.get("in_seconds", 0)), "-i", str(path), "-map", "0:v:0", "-an",
            "-vf", fit, "-frames:v", str(scene["duration_frames"]), "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.decoder_log = self.decoder.stderr

    def frame(self, index: int) -> Image.Image:
        scene = next(s for s in self.spec["scenes"] if s["start_frame"] <= index < s["start_frame"] + s["duration_frames"])
        if scene["id"] != self.scene_id:
            self._begin(scene)
        if self.image is not None:
            return self.image.copy()
        if self.decoder is None:
            return self.renderer.render_background(index)
        raw = self.decoder.stdout.read(self.size[0] * self.size[1] * 3)
        if len(raw) != self.size[0] * self.size[1] * 3:
            self.close()
            raise ValueError(f"Source ran out at timeline frame {index}; render stopped instead of duplicating frames")
        return Image.frombytes("RGB", self.size, raw)


class Encoder:
    def __init__(self, path: Path, video: dict, kind: str):
        self.path = path
        self.log_path = path.with_suffix(path.suffix + ".log")
        self.log = self.log_path.open("wb")
        alpha = kind == "graphics"
        args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba" if alpha else "rgb24",
                "-s", f"{video['width']}x{video['height']}", "-framerate", str(video["fps"]), "-i", "pipe:0", "-an",
                "-threads", "2", "-filter_threads", "1", "-vf", "scale=out_color_matrix=bt709:out_range=tv,setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709",
                "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv"]
        if kind == "review":
            args += ["-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        else:
            args += ["-c:v", "prores_ks", "-profile:v", "4" if alpha else "3", "-vendor", "apl0",
                     "-pix_fmt", "yuva444p10le" if alpha else "yuv422p10le"]
            if alpha:
                args += ["-alpha_bits", "16"]
            args += ["-bsf:v", "prores_metadata=color_primaries=bt709:color_trc=bt709:colorspace=bt709",
                     "-movflags", "+write_colr", "-timecode", "00:00:00:00"]
        self.process = subprocess.Popen(args + [str(path)], stdin=subprocess.PIPE, stderr=self.log, stdout=subprocess.DEVNULL)
        self.closed = False

    def write(self, image: Image.Image):
        try:
            self.process.stdin.write(image.tobytes())
        except BrokenPipeError as exc:
            raise RuntimeError(f"Encoder stopped: {self.log_path.read_text(errors='replace')[-3000:]}") from exc

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.process.stdin.close()
        except BrokenPipeError:
            pass
        status = self.process.wait()
        self.log.close()
        if status:
            raise RuntimeError(f"Encoding {self.path.name} failed: {self.log_path.read_text(errors='replace')[-3000:]}")

    def abort(self):
        if not self.closed:
            self.process.kill()
            self.process.wait()
            self.log.close()
            self.closed = True
