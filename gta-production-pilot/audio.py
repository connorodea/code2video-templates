"""Offline speech, original procedural score/SFX, and sample-aligned WAV stems."""
from __future__ import annotations

import ctypes as C
import ctypes.util
import json
import math
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from captions import load_words, validate_words


SAMPLE_RATE = 48000


def _number(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f"{label} must be a finite number >= {minimum}")
    return float(value)


def _local_file(value, base):
    if not isinstance(value, str) or "://" in value or value.startswith(("data:", "pipe:", "concat:", "file:")):
        raise ValueError("Audio and caption inputs must be local filesystem paths")
    path = Path(value).expanduser()
    path = (Path(base) / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_file():
        raise ValueError(f"Input file does not exist: {path}")
    return path


def _decode_audio(path, ffmpeg):
    """Decode local audio once; protocol whitelist prevents network inputs."""
    result = subprocess.run([str(ffmpeg), "-v", "error", "-nostdin", "-protocol_whitelist", "file,pipe",
                             "-i", str(path), "-map", "0:a:0", "-vn", "-ar", str(SAMPLE_RATE),
                             "-ac", "2", "-f", "f32le", "pipe:1"], capture_output=True)
    if result.returncode:
        raise ValueError(f"FFmpeg could not decode narration: {result.stderr.decode(errors='replace').strip()}")
    if not result.stdout or len(result.stdout) % 8:
        raise ValueError("Narration decoded to empty or invalid stereo audio")
    samples = np.frombuffer(result.stdout, dtype="<f4").reshape(-1, 2).copy()
    if not np.isfinite(samples).all():
        raise ValueError("Narration contains non-finite audio samples")
    return samples


class _Flite:
    """Small binding to Flite's native waveform and utterance word relations."""
    def __init__(self, voice):
        if voice not in {"slt", "rms", "awb", "kal", "kal16"}:
            raise ValueError("Synthetic voice must be slt, rms, awb, kal, or kal16")
        self.libraries = []
        try:
            for name in ("flite", "flite_usenglish", "flite_cmulex", f"flite_cmu_us_{voice}"):
                library = ctypes.util.find_library(name)
                if library is None:
                    raise OSError(f"Cannot locate {name}")
                self.libraries.append(C.CDLL(library, mode=C.RTLD_GLOBAL))
            self.lib = self.libraries[0]
            self.lib.flite_init.argtypes = []
            self.lib.flite_init.restype = C.c_int
            self.lib.flite_init()
            register = getattr(self.libraries[-1], f"register_cmu_us_{voice}")
            register.argtypes, register.restype = [C.c_char_p], C.c_void_p
            self.voice = register(None)
            if not self.voice:
                raise OSError("Flite voice registration failed")
            definitions = [
                ("flite_synth_text", [C.c_char_p, C.c_void_p], C.c_void_p),
                ("utt_relation", [C.c_void_p, C.c_char_p], C.c_void_p),
                ("relation_head", [C.c_void_p], C.c_void_p),
                ("item_next", [C.c_void_p], C.c_void_p),
                ("item_feat_string", [C.c_void_p, C.c_char_p], C.c_char_p),
                ("ffeature_float", [C.c_void_p, C.c_char_p], C.c_float),
                ("utt_wave", [C.c_void_p], C.c_void_p),
                ("cst_wave_save_riff", [C.c_void_p, C.c_char_p], C.c_int),
                ("delete_utterance", [C.c_void_p], None),
            ]
            for name, args, result in definitions:
                function = getattr(self.lib, name)
                function.argtypes, function.restype = args, result
        except (OSError, AttributeError) as exc:
            raise RuntimeError("Offline demo narration requires native Flite libraries and an installed voice "
                               "(for example Debian/Ubuntu package libflite1). Install them locally, or use "
                               "narration.mode='file' with local audio and timestamps. No download is performed.") from exc
        self.voice_name = voice

    def synthesize(self, text, output):
        if not isinstance(text, str) or not text.strip() or "\x00" in text:
            raise ValueError("Narration text must be nonempty and cannot contain NUL")
        utterance = self.lib.flite_synth_text(text.encode("utf-8"), self.voice)
        if not utterance:
            raise RuntimeError("Flite did not produce an utterance")
        try:
            relation = self.lib.utt_relation(utterance, b"Word")
            if not relation:
                raise RuntimeError("Flite utterance has no word relation")
            item, words = self.lib.relation_head(relation), []
            while item:
                name = self.lib.item_feat_string(item, b"name")
                start = float(self.lib.ffeature_float(item, b"R:SylStructure.daughter1.daughter1.R:Segment.p.end"))
                end = float(self.lib.ffeature_float(item, b"R:SylStructure.daughtern.daughtern.end"))
                words.append({"word": name.decode("utf-8") if name else "", "start": start, "end": end})
                item = self.lib.item_next(item)
            # Preserve punctuation/case only when token identities actually align.
            tokens = text.split()
            lexical = lambda value: re.sub(r"[^\w']", "", value, flags=re.UNICODE).casefold()
            preserved = len(tokens) == len(words) and all(lexical(t) == lexical(w["word"]) for t, w in zip(tokens, words))
            if preserved:
                for word, token in zip(words, tokens):
                    word["word"] = token
            if self.lib.cst_wave_save_riff(self.lib.utt_wave(utterance), str(output).encode()) != 0:
                raise RuntimeError("Flite could not write its synthesized waveform")
            return validate_words(words), preserved
        finally:
            self.lib.delete_utterance(utterance)


def _flite_version():
    if shutil.which("dpkg-query"):
        result = subprocess.run(["dpkg-query", "-W", "-f=${Version}", "libflite1"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    return "native installed library; package version unavailable"


def _envelope(length, attack, release):
    result = np.ones(length, dtype=np.float32)
    attack, release = min(length, attack), min(length, release)
    if attack:
        result[:attack] *= np.linspace(0, 1, attack, dtype=np.float32)
    if release:
        result[-release:] *= np.linspace(1, 0, release, dtype=np.float32)
    return result


def _music(length, bpm, seed):
    """An original quiet synth bed with a bass pulse and sparse stereo arpeggio."""
    rng = np.random.default_rng(seed)
    t = np.arange(length, dtype=np.float64) / SAMPLE_RATE
    beat = 60 / bpm
    progression = np.array([55.0, 65.4064, 48.9994, 43.6535])
    frequency = progression[(t // (beat * 4)).astype(int) % 4]
    phase = 2 * np.pi * np.cumsum(frequency) / SAMPLE_RATE
    pulse = np.exp(-((t % beat) / .20))
    bass = .45 * np.sin(phase) * (.35 + .65 * pulse)
    pad = .17 * np.sin(phase * 2) + .09 * np.sin(phase * 3)
    left, right = bass + pad, bass + pad
    music = np.stack([left, right], axis=1).astype(np.float32)
    for index, onset in enumerate(np.arange(0, length / SAMPLE_RATE, beat / 2)):
        start = round(onset * SAMPLE_RATE)
        count = min(round(beat * .95 * SAMPLE_RATE), length - start)
        if count <= 0:
            break
        local = np.arange(count) / SAMPLE_RATE
        note = progression[int(onset // (beat * 4)) % 4] * [4, 6, 8, 12][index % 4]
        tone = .13 * np.sin(2 * np.pi * note * local) * np.exp(-local / .13)
        tone *= _envelope(count, 240, 1200)
        pan = .25 if index % 2 else .75
        music[start:start + count, 0] += tone * math.sqrt(1 - pan)
        music[start:start + count, 1] += tone * math.sqrt(pan)
    # Deterministic soft noise texture; no third-party samples or compositions.
    texture = rng.normal(0, .002, (length, 2)).astype(np.float32)
    music += texture
    music *= _envelope(length, SAMPLE_RATE // 2, SAMPLE_RATE)[:, None]
    return music


def _duck_envelope(length, words):
    gain = np.ones(length, dtype=np.float32)
    attack, release, depth = int(.10 * SAMPLE_RATE), int(.20 * SAMPLE_RATE), .30
    for word in words:
        start, end = round(word["start"] * SAMPLE_RATE), round(word["end"] * SAMPLE_RATE)
        start, end = max(0, start), min(length, end)
        a, b = max(0, start - attack), min(length, end + release)
        if a < start:
            gain[a:start] = np.minimum(gain[a:start], np.linspace(1, depth, start - a, endpoint=False))
        gain[start:end] = np.minimum(gain[start:end], depth)
        if end < b:
            gain[end:b] = np.minimum(gain[end:b], np.linspace(depth, 1, b - end))
    return gain


def _sfx(length, scenes, fps, seed):
    result = np.zeros((length, 2), dtype=np.float32)
    rng = np.random.default_rng(seed + 101)
    events = []
    for scene in scenes:
        frame = scene["start_frame"]
        if frame == 0 or scene.get("transition_in", "cut") == "cut":
            continue
        start = round(frame * SAMPLE_RATE / fps)
        count = min(length - start, round(max(.18, scene.get("transition_frames", 12) / fps) * SAMPLE_RATE))
        if count <= 1:
            continue
        t = np.arange(count) / SAMPLE_RATE
        noise = rng.normal(0, 1, count)
        smooth = np.convolve(noise, np.ones(9) / 9, mode="same")
        chirp = np.sin(2 * np.pi * (260 * t + 600 * t * t))
        whoosh = (.32 * smooth + .12 * chirp) * np.sin(np.linspace(0, np.pi, count)) ** 2
        pan = np.linspace(.15, .85, count)
        result[start:start + count, 0] += whoosh * np.sqrt(1 - pan)
        result[start:start + count, 1] += whoosh * np.sqrt(pan)
        events.append({"kind": "transition-sfx", "frame": frame, "sample": start,
                       "duration_samples": count, "scene_id": scene.get("id", "")})
    return result, events


def _write_wav(path, samples):
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if not math.isfinite(peak) or peak >= 1:
        raise ValueError(f"Refusing to write clipping/non-finite stem {path.name} (peak={peak})")
    pcm = np.rint(samples * 32767).astype("<i2")
    with wave.open(str(path), "wb") as target:
        target.setnchannels(2)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(pcm.tobytes())
    return {"peak": peak, "peak_dbfs": round(20 * math.log10(peak), 3) if peak else None,
            "rms": float(np.sqrt(np.mean(samples.astype(np.float64) ** 2))),
            "samples_per_channel": len(samples), "channels": 2, "sample_rate": SAMPLE_RATE, "pcm_bits": 16}


def prepare_audio(spec, config_dir, out_dir, ffmpeg="ffmpeg"):
    """Produce full-duration 48 kHz stereo PCM16 narration/music/SFX/mix stems."""
    video, settings, narration_spec = spec["video"], spec["audio"], spec["narration"]
    fps = _number(video["fps"], "video.fps", 1)
    frames = _number(video["duration_frames"], "video.duration_frames", 1)
    if settings.get("sample_rate", SAMPLE_RATE) != SAMPLE_RATE:
        raise ValueError("Resolve stems use sample_rate=48000")
    duration = frames / fps
    length = round(duration * SAMPLE_RATE)
    gains = {name: _number(settings.get(f"{name}_gain", default), f"audio.{name}_gain")
             for name, default in (("voice", .85), ("music", .11), ("sfx", .32))}
    bpm = _number(settings.get("bpm", 100), "audio.bpm", 1)
    seed = spec.get("project", {}).get("seed", 7)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("project.seed must be a nonnegative integer")
    out_dir = Path(out_dir).resolve()
    stem_dir = out_dir / "resolve"
    stem_dir.mkdir(parents=True, exist_ok=True)
    narration = np.zeros((length, 2), dtype=np.float32)
    words, events, line_reports = [], [], []
    mode = narration_spec.get("mode")
    if mode == "synthetic":
        engine = _Flite(narration_spec.get("voice", "slt"))
        lines = narration_spec.get("lines")
        if not isinstance(lines, list) or not lines:
            raise ValueError("Synthetic narration requires at least one line")
        previous_end = 0
        with tempfile.TemporaryDirectory(prefix="gta-flite-") as temporary:
            for index, line in enumerate(lines):
                frame = line.get("start_frame")
                if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
                    raise ValueError("Narration start_frame must be a nonnegative integer")
                start = round(frame * SAMPLE_RATE / fps)
                if start < previous_end:
                    raise ValueError(f"Narration line {index} overlaps the previous line's audio")
                raw_path = Path(temporary) / f"line-{index}.wav"
                native_words, preserved = engine.synthesize(line.get("text"), raw_path)
                samples = _decode_audio(raw_path, ffmpeg)
                end = start + len(samples)
                if end > length:
                    raise ValueError(f"Narration line {index} ends beyond the timeline; shorten it or extend video.duration_frames")
                narration[start:end] = samples
                offset = start / SAMPLE_RATE
                words.extend({**word, "start": word["start"] + offset, "end": word["end"] + offset} for word in native_words)
                events.append({"kind": "narration-line-start", "frame": frame, "sample": start, "line": index})
                line_reports.append({"line": index, "start_sample": start, "end_sample": end,
                                     "input_text": line["text"], "original_tokens_preserved": preserved})
                previous_end = end
        source = "flite-native-word-boundaries"
        backend = {"name": "Flite native utterance relations", "version": _flite_version(), "voice": engine.voice_name}
    elif mode == "file":
        path = _local_file(narration_spec.get("path"), config_dir)
        caption_path = _local_file(narration_spec.get("captions_path"), config_dir)
        offset = _number(narration_spec.get("offset_seconds", 0), "narration.offset_seconds")
        start = round(offset * SAMPLE_RATE)
        samples = _decode_audio(path, ffmpeg)
        end = start + len(samples)
        if end > length:
            raise ValueError(f"Narration audio ends at {end / SAMPLE_RATE:.6f}s beyond the {duration:.6f}s timeline; no audio was truncated")
        narration[start:end] = samples
        words, source = load_words(caption_path, format=narration_spec.get("captions_format", "auto"),
                                   channel=narration_spec.get("channel", 0), offset_seconds=offset,
                                   duration_seconds=duration)
        # Word times must refer to the supplied audio, not padded tail silence.
        if words[-1]["end"] > end / SAMPLE_RATE + 1 / SAMPLE_RATE:
            raise ValueError("Caption word times extend beyond the supplied narration audio")
        backend = {"name": "local audio file", "source_file": str(path), "caption_file": str(caption_path),
                   "offset_seconds": offset, "offset_samples": start, "source_samples": len(samples)}
    else:
        raise ValueError("narration.mode must be 'synthetic' or 'file'")
    words = validate_words(words, duration)
    narration *= gains["voice"]
    # Remove only possible boundary clicks, without changing caption timing.
    narration *= _envelope(length, 48, 48)[:, None]
    duck = _duck_envelope(length, words)
    music = _music(length, bpm, seed) * (duck * gains["music"])[:, None]
    sfx, sfx_events = _sfx(length, spec.get("scenes", []), fps, seed)
    sfx *= gains["sfx"]
    events.extend(sfx_events)
    mix = narration + music + sfx
    peak = max(float(np.max(np.abs(array))) for array in (narration, music, sfx, mix))
    # One shared attenuation retains stem summation and relative mix levels.
    headroom_gain = min(1.0, .95 / peak) if peak else 1.0
    stems, measures = {}, {}
    for name, samples in (("narration", narration), ("music", music), ("sfx", sfx), ("mix", mix)):
        samples *= headroom_gain
        path = stem_dir / f"{name}.wav"
        measures[name] = _write_wav(path, samples)
        stems[name] = str(path)
    (out_dir / "words.json").write_text(json.dumps(words, indent=2) + "\n", encoding="utf-8")
    ffmpeg_version = subprocess.run([str(ffmpeg), "-version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    return {"words": words, "timing_source": source, "stems": stems, "sample_rate": SAMPLE_RATE,
            "duration_samples": length, "duration_seconds": length / SAMPLE_RATE, "channels": 2,
            "pcm_bits": 16, "backend": backend, "ffmpeg_version": ffmpeg_version,
            "sync_events": sorted(events, key=lambda event: event["sample"]), "lines": line_reports,
            "word_sample_timings": [{"word": word["word"], "start_sample": round(word["start"] * SAMPLE_RATE),
                                      "end_sample": round(word["end"] * SAMPLE_RATE)} for word in words],
            "measures": measures, "mix_settings": {**gains, "bpm": bpm, "seed": seed,
                "shared_headroom_gain": headroom_gain, "music_duck_gain": .30, "duck_attack_seconds": .10,
                "duck_release_seconds": .20, "music_fade_in_seconds": .5, "music_fade_out_seconds": 1.0},
            "provenance": {"music": "Original deterministic procedural synthesis in audio.py; no external samples.",
                           "sfx": "Original deterministic procedural synthesis in audio.py; no external samples.",
                           "narration": "Offline Flite synthesized demonstration text; installed engine/voice licenses apply."
                           if mode == "synthetic" else "User-supplied local narration; source rights remain with its owner.",
                           "paid_generation_calls": 0}}
