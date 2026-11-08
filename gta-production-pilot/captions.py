"""Offline caption adapters; all normalized timestamps are timeline seconds."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def validate_words(words, duration_seconds=None):
    """Return canonical words, rejecting invalid, reversed, or overlapping times."""
    if not isinstance(words, list) or not words:
        raise ValueError("Captions must contain a nonempty list of words")
    limit = None if duration_seconds is None else _number(duration_seconds, "duration_seconds")
    if limit is not None and limit <= 0:
        raise ValueError("duration_seconds must be positive")
    normalized = []
    previous_end = 0.0
    for index, item in enumerate(words):
        if not isinstance(item, dict):
            raise ValueError(f"word[{index}] must be an object")
        text = item.get("punctuated_word") or item.get("word") or item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"word[{index}] must have nonempty text")
        start = _number(item.get("start"), f"word[{index}].start")
        end = _number(item.get("end"), f"word[{index}].end")
        if start < 0 or end <= start:
            raise ValueError(f"word[{index}] requires 0 <= start < end")
        if start < previous_end:
            raise ValueError(f"word[{index}] overlaps or precedes the previous word")
        if limit is not None and end > limit:
            raise ValueError(f"word[{index}] ends beyond the video timeline ({limit}s)")
        normalized.append({"word": " ".join(text.split()), "start": start, "end": end})
        previous_end = end
    return normalized


def _spread_phrase(text, start, end):
    if not isinstance(text, str):
        raise ValueError("Caption phrase text must be a string")
    tokens = text.split()
    if not tokens:
        raise ValueError("Caption phrase must contain text")
    start = _number(start, "phrase.start")
    end = _number(end, "phrase.end")
    if start < 0 or end <= start:
        raise ValueError("Caption phrase requires 0 <= start < end")
    step = (end - start) / len(tokens)
    return [{"word": token, "start": start + i * step,
             "end": end if i == len(tokens) - 1 else start + (i + 1) * step}
            for i, token in enumerate(tokens)]


_SRT_TIME = re.compile(r"^(\d+):(\d{2}):(\d{2})[,.](\d{3})$")


def _srt_seconds(value):
    match = _SRT_TIME.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value!r}")
    hours, minutes, seconds, millis = map(int, match.groups())
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"Invalid SRT timestamp: {value!r}")
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def _read_srt(text):
    words = []
    for block in re.split(r"\n[ \t]*\n", text.lstrip("\ufeff").replace("\r\n", "\n").strip()):
        lines = block.splitlines()
        if lines and lines[0].strip().isdigit():
            lines.pop(0)
        if len(lines) < 2 or "-->" not in lines[0]:
            raise ValueError("Each SRT cue needs a timestamp line and caption text")
        start, end = lines[0].split("-->", 1)
        phrase = re.sub(r"</?(?:i|b|u|font)\b[^>]*>", "", " ".join(lines[1:]), flags=re.IGNORECASE)
        words.extend(_spread_phrase(phrase, _srt_seconds(start), _srt_seconds(end)))
    return words


def load_words(path, format="auto", channel=0, offset_seconds=0, duration_seconds=None):
    """Read Deepgram, words/segments JSON, or SRT without making an API call.

    SRT phrase intervals are interpolated and explicitly labeled approximate;
    supplied Deepgram/word timestamps are preserved except for the requested offset.
    """
    if format not in {"auto", "deepgram", "words", "srt"}:
        raise ValueError(f"Unsupported captions format: {format}")
    if isinstance(channel, bool) or not isinstance(channel, int) or channel < 0:
        raise ValueError("channel must be a nonnegative integer")
    offset = _number(offset_seconds, "offset_seconds")
    if offset < 0:
        raise ValueError("offset_seconds must be nonnegative")
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if format == "srt" or (format == "auto" and path.suffix.lower() == ".srt"):
        words, source = _read_srt(text), "srt-phrase-interpolated-approximate"
    else:
        def reject_constant(value):
            raise ValueError(f"Non-finite JSON number: {value}")
        data = json.loads(text, parse_constant=reject_constant)
        is_deepgram = isinstance(data, dict) and isinstance(data.get("results"), dict) and "channels" in data["results"]
        if format == "deepgram" or (format == "auto" and is_deepgram):
            try:
                words = data["results"]["channels"][channel]["alternatives"][0]["words"]
            except (KeyError, IndexError, TypeError) as exc:
                raise ValueError(f"Deepgram response has no words for channel {channel}, alternative 0") from exc
            source = "deepgram-word-timestamps"
        elif isinstance(data, list):
            words, source = data, "provided-word-timestamps"
        elif isinstance(data, dict) and "words" in data:
            words, source = data["words"], "provided-word-timestamps"
        elif isinstance(data, dict) and isinstance(data.get("segments"), list):
            words, approximate = [], False
            for segment in data["segments"]:
                if not isinstance(segment, dict):
                    raise ValueError("Each caption segment must be an object")
                if "words" in segment:
                    if not isinstance(segment["words"], list):
                        raise ValueError("segment.words must be a list")
                    words.extend(segment["words"])
                else:
                    words.extend(_spread_phrase(segment.get("text", ""), segment.get("start"), segment.get("end")))
                    approximate = True
            source = "segment-phrase-interpolated-approximate" if approximate else "provided-segment-word-timestamps"
        else:
            raise ValueError("Expected Deepgram results.channels, a word list, words, or segments")
    words = validate_words(words)
    shifted = [{**word, "start": word["start"] + offset, "end": word["end"] + offset} for word in words]
    return validate_words(shifted, duration_seconds), source


def chunk_words(words, max_words=4, gap_seconds=.45):
    """Group timed words without stretching a cue over a long silent gap."""
    words = validate_words(words)
    if isinstance(max_words, bool) or not isinstance(max_words, int) or max_words < 1:
        raise ValueError("max_words must be a positive integer")
    gap = _number(gap_seconds, "gap_seconds")
    if gap < 0:
        raise ValueError("gap_seconds must be nonnegative")
    groups, current = [], []
    for word in words:
        if current and (len(current) >= max_words or word["start"] - current[-1]["end"] > gap
                        or re.search(r"[.!?][\"')\]]?$", current[-1]["word"])):
            groups.append(current)
            current = []
        current.append(word)
    if current:
        groups.append(current)
    return [{"text": " ".join(w["word"] for w in group), "start": group[0]["start"],
             "end": group[-1]["end"], "words": group} for group in groups]


def write_srt(chunks, path):
    def timestamp(milliseconds):
        hours, rest = divmod(milliseconds, 3600000)
        minutes, rest = divmod(rest, 60000)
        seconds, millis = divmod(rest, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
    lines, previous_end = [], 0.0
    for index, cue in enumerate(chunks, 1):
        start = _number(cue.get("start"), "cue.start")
        end = _number(cue.get("end"), "cue.end")
        text = cue.get("text")
        if start < previous_end or start < 0 or end <= start or not isinstance(text, str) or not text.strip():
            raise ValueError("SRT cues must have ordered nonoverlapping times and nonempty text")
        start_ms, end_ms = round(start * 1000), round(end * 1000)
        if end_ms <= start_ms:
            raise ValueError("SRT cue duration is too short for millisecond precision")
        lines.extend([str(index), f"{timestamp(start_ms)} --> {timestamp(end_ms)}", text.strip(), ""])
        previous_end = end
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
