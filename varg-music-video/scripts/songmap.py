#!/usr/bin/env python3
"""Song map: BPM, beats, downbeats (4/4) and optional word timings → songmap.json.

  python3 songmap.py assets/song.mp3 --out songmap.json [--lyrics lyrics.txt] [--whisper small] [--start 30.692 --end 129.712]

Beats/downbeats: librosa beat tracking; the bar phase is the one whose beats carry the most onset strength.
Words: faster-whisper with word timestamps, the lyrics as the initial prompt (optional; skip with no --lyrics/--whisper).
Sections, drops and fixes are written in by hand afterwards (see references/anime-case-study.md in the
varg-music-video skill: https://github.com/vargHQ/skills/tree/main/varg-music-video)."""
import argparse, json, subprocess, tempfile
from pathlib import Path

import librosa
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("audio")
ap.add_argument("--out", default="songmap.json")
ap.add_argument("--lyrics", help="plain-text lyrics, one line per sung line ([Section] lines are skipped)")
ap.add_argument("--whisper", default=None, help="faster-whisper model for word timings (tiny/small/medium/large-v3)")
ap.add_argument("--start", type=float, default=0.0, help="use a window of a longer track: start (s)")
ap.add_argument("--end", type=float, default=None, help="window end (s)")
ap.add_argument("--bpm", type=float, default=None, help="known BPM (from the generator/DAW): only the phase is fitted")
a = ap.parse_args()

y, sr = librosa.load(a.audio, sr=22050, offset=a.start, duration=(a.end - a.start) if a.end else None)
dur = len(y) / sr
HOP = 512
env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
env_t = librosa.times_like(env, sr=sr, hop_length=HOP)
tempo, _ = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=HOP)
est = a.bpm or float(np.atleast_1d(tempo)[0])

# AI songs sit on a fixed tempo, but the phase can jump between sections. Score each candidate tempo by the best
# phase inside every 8 s window (onset energy landing on the grid), then let beat_track follow that tempo tightly.
# (librosa's own estimate was 3.5 % off on the reference track: 129.2 instead of 133.8.)
def window_score(bpm, win=8.0):
    p = 60.0 / bpm; total = []
    for w0 in np.arange(0, max(dur - win, 0) + 1e-6, win):
        best = 0
        for ph in np.arange(0, p, 0.01):
            t = np.arange(w0 + ph, min(w0 + win, dur), p)
            best = max(best, env[np.clip(np.searchsorted(env_t, t), 0, len(env) - 1)].mean())
        total.append(best)
    return float(np.mean(total))

cands = [est] if a.bpm else [b for b in np.arange(est * 0.94, est * 1.06, 0.1)]
bpm = max(cands, key=window_score)
if not a.bpm:                                            # refine around the winner
    bpm = max(np.arange(bpm - 0.1, bpm + 0.1, 0.02), key=window_score)
_, frames = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=HOP, start_bpm=bpm, tightness=400)
beats = librosa.frames_to_time(frames, sr=sr, hop_length=HOP)
strength = env[np.clip(np.searchsorted(env_t, beats), 0, len(env) - 1)]
bar = int(np.argmax([strength[k::4].mean() if len(strength[k::4]) else 0 for k in range(4)]))
downbeats = beats[bar::4]

sm = {"bpm": round(bpm, 2), "duration": round(dur, 3), "master": a.audio,
      "source": {"file": a.audio, "window": [a.start, a.end]},
      "beats": [round(float(t), 3) for t in beats], "downbeats": [round(float(t), 3) for t in downbeats],
      "sections": [], "drops": [], "words": [], "lines": []}

if a.lyrics or a.whisper:
    from faster_whisper import WhisperModel
    src = a.audio
    if a.start or a.end:                                      # transcribe the window only
        src = str(Path(tempfile.mkdtemp()) / "win.wav")
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(a.start), "-i", a.audio] + (["-t", str(a.end - a.start)] if a.end else []) + [src]
        subprocess.run(cmd, check=True)
    lines = [l.strip() for l in open(a.lyrics).read().splitlines() if l.strip() and not l.startswith("[")] if a.lyrics else []
    model = WhisperModel(a.whisper or "small", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(src, word_timestamps=True, initial_prompt=" ".join(lines)[:800] or None, beam_size=5)
    words = [{"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)} for s in segs for w in s.words if w.word.strip()]
    # assign words to lyric lines in order (by word count); unmatched words keep line -1
    k = 0
    for i, line in enumerate(lines):
        for _ in line.split():
            if k < len(words):
                words[k]["line"] = i; k += 1
    for w in words:
        w.setdefault("line", -1)
    sm["words"] = words
    for i, line in enumerate(lines):
        ww = [w for w in words if w["line"] == i]
        if ww:
            sm["lines"].append({"i": i, "text": line, "start": ww[0]["start"], "end": ww[-1]["end"]})

json.dump(sm, open(a.out, "w"), indent=1, ensure_ascii=False)
print(f"{a.out}: {bpm:.1f} BPM, {len(beats)} beats, {len(downbeats)} downbeats, {len(sm['words'])} words, {dur:.2f} s")
