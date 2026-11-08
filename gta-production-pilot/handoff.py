#!/usr/bin/env python3
"""Write a portable, frame-exact Final Cut Pro 7 XML handoff for Resolve.

Only the Python standard library is required.  Run this copy after moving an
export to another computer: ``python3 handoff.py --out /path/to/export``.
The media is rendered elsewhere; this module does not launch Resolve and an
XML structure check does not prove that a particular Resolve version imports it.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Any
import xml.etree.ElementTree as ET


MEDIA = {
    "clean": "resolve/clean.mov",
    "graphics": "resolve/graphics.mov",
    "narration": "resolve/narration.wav",
    "music": "resolve/music.wav",
    "sfx": "resolve/sfx.wav",
}


def _node(parent: ET.Element, tag: str, value: Any | None = None, **attrs: str) -> ET.Element:
    element = ET.SubElement(parent, tag, attrs)
    if value is not None:
        element.text = str(value)
    return element


def _rate(parent: ET.Element, fps: int) -> None:
    rate = _node(parent, "rate")
    _node(rate, "timebase", fps)
    _node(rate, "ntsc", "FALSE")


def _timecode(parent: ET.Element, fps: int) -> None:
    timecode = _node(parent, "timecode")
    _rate(timecode, fps)
    _node(timecode, "string", "00:00:00:00")
    _node(timecode, "frame", 0)
    _node(timecode, "displayformat", "NDF")


def _video_characteristics(parent: ET.Element, video: dict[str, Any]) -> None:
    sample = _node(parent, "samplecharacteristics")
    _rate(sample, video["fps"])
    _node(sample, "width", video["width"])
    _node(sample, "height", video["height"])
    _node(sample, "anamorphic", "FALSE")
    _node(sample, "pixelaspectratio", "square")
    _node(sample, "fielddominance", "none")


def _audio_characteristics(parent: ET.Element) -> None:
    sample = _node(parent, "samplecharacteristics")
    _node(sample, "depth", 16)
    _node(sample, "samplerate", 48000)


def _file(parent: ET.Element, key: str, path: Path, video: dict[str, Any],
          defined: set[str]) -> None:
    file_id = f"file-{key}"
    element = _node(parent, "file", id=file_id)
    if file_id in defined:
        return
    defined.add(file_id)
    _node(element, "name", path.name)
    _node(element, "pathurl", path.resolve().as_uri())
    _rate(element, video["fps"])
    _node(element, "duration", video["duration_frames"])
    _timecode(element, video["fps"])
    media = _node(element, "media")
    if key in ("clean", "graphics"):
        _video_characteristics(_node(media, "video"), video)
    else:
        audio = _node(media, "audio")
        _audio_characteristics(audio)
        _node(audio, "channelcount", 2)
        _node(audio, "layout", "stereo")


def _validate_inputs(spec: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    """Check the handoff contract without importing the rendering dependencies."""
    if not isinstance(spec, dict) or not isinstance(spec.get("video"), dict):
        raise ValueError("The resolved spec must contain a video object")
    video = spec["video"]
    for field in ("width", "height", "fps", "duration_frames"):
        value = video.get(field)
        if type(value) is not int or value <= 0:
            raise ValueError(f"video.{field} must be a positive integer")
    if video["fps"] not in (24, 25, 30, 50, 60):
        raise ValueError("Handoff supports integer 24, 25, 30, 50, or 60 fps")
    scenes = spec.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("The resolved spec must contain at least one scene")
    expected_start = 0
    seen: set[str] = set()
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            raise ValueError(f"scenes[{index}] must be an object")
        scene_id = scene.get("id")
        if not isinstance(scene_id, str) or not scene_id or scene_id in seen:
            raise ValueError("Scene ids must be unique nonempty strings")
        seen.add(scene_id)
        start, duration = scene.get("start_frame"), scene.get("duration_frames")
        if type(start) is not int or start != expected_start:
            raise ValueError(f"Scene {scene_id!r} must start at frame {expected_start}")
        if type(duration) is not int or duration <= 0:
            raise ValueError(f"Scene {scene_id!r} needs a positive integer duration")
        expected_start += duration
    if expected_start != video["duration_frames"]:
        raise ValueError("Scenes must exactly cover video.duration_frames")
    missing = [str(out_dir / relative) for relative in MEDIA.values()
               if not (out_dir / relative).is_file()]
    if missing:
        raise FileNotFoundError("Missing handoff media: " + ", ".join(missing))
    return video


def write_handoff(spec: dict[str, Any], out_dir: Path) -> Path:
    """Write timeline.xml for pre-rendered masters and three stereo audio stems.

    V1 is the clean master, V2 the straight-alpha graphics master. Both tracks
    are cut at scene boundaries with identical timeline/source frame ranges.
    Each stereo WAV is represented by a linked pair of mono source channels
    (six timeline channels, three independent stems). All media starts at zero.
    Captions remain a separate SRT, and titles remain editable through JSON and
    re-rendering; they are not native Resolve title generators.
    """
    out_dir = Path(out_dir).expanduser().resolve()
    video = _validate_inputs(spec, out_dir)
    fps, total = video["fps"], video["duration_frames"]
    project = spec.get("project", {})
    title = str(project.get("title", "GTA Production Pilot"))
    root = ET.Element("xmeml", {"version": "5"})
    sequence = _node(root, "sequence", id="sequence-gta-pilot")
    _node(sequence, "name", title)
    _node(sequence, "duration", total)
    _rate(sequence, fps)
    _timecode(sequence, fps)
    media = _node(sequence, "media")
    video_element = _node(media, "video")
    _video_characteristics(_node(video_element, "format"), video)
    defined: set[str] = set()

    for layer in ("clean", "graphics"):
        track = _node(video_element, "track")
        for index, scene in enumerate(spec["scenes"], start=1):
            start = scene["start_frame"]
            end = start + scene["duration_frames"]
            clip = _node(track, "clipitem", id=f"clip-{layer}-{index}")
            _node(clip, "name", f"{scene['id']} / {layer}")
            _node(clip, "enabled", "TRUE")
            _node(clip, "duration", total)
            _rate(clip, fps)
            _node(clip, "start", start)
            _node(clip, "end", end)
            _node(clip, "in", start)
            _node(clip, "out", end)
            _node(clip, "alphatype", "straight" if layer == "graphics" else "none")
            _node(clip, "pixelaspectratio", "square")
            _node(clip, "anamorphic", "FALSE")
            _file(clip, layer, out_dir / MEDIA[layer], video, defined)
            source = _node(clip, "sourcetrack")
            _node(source, "mediatype", "video")
            _node(source, "trackindex", 1)
        _node(track, "enabled", "TRUE")
        _node(track, "locked", "FALSE")

    audio = _node(media, "audio")
    _node(audio, "channelcount", 2)
    _audio_characteristics(_node(audio, "format"))
    outputs = _node(audio, "outputs")
    output_group = _node(outputs, "group")
    _node(output_group, "index", 1)
    _node(output_group, "numchannels", 2)
    _node(output_group, "downmix", 0)
    for channel in (1, 2):
        _node(_node(output_group, "channel"), "index", channel)

    for stem_index, stem in enumerate(("narration", "music", "sfx")):
        for channel in (1, 2):
            track = _node(audio, "track")
            clip_id = f"clip-{stem}-{channel}"
            clip = _node(track, "clipitem", id=clip_id)
            _node(clip, "name", f"{stem} / {'L' if channel == 1 else 'R'}")
            _node(clip, "enabled", "TRUE")
            _node(clip, "duration", total)
            _rate(clip, fps)
            _node(clip, "start", 0)
            _node(clip, "end", total)
            _node(clip, "in", 0)
            _node(clip, "out", total)
            _file(clip, stem, out_dir / MEDIA[stem], video, defined)
            source = _node(clip, "sourcetrack")
            _node(source, "mediatype", "audio")
            _node(source, "trackindex", channel)
            for linked_channel in (1, 2):
                link = _node(clip, "link")
                _node(link, "linkclipref", f"clip-{stem}-{linked_channel}")
                _node(link, "mediatype", "audio")
                _node(link, "trackindex", stem_index * 2 + linked_channel)
                _node(link, "clipindex", 1)
                # Group indices are local to this clip's link array. Each
                # array contains exactly one stereo pair, regardless of stem.
                _node(link, "groupindex", 1)
            _node(track, "enabled", "TRUE")
            _node(track, "locked", "FALSE")
            _node(track, "outputchannelindex", channel)

    ET.indent(root, space="  ")
    data = b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n'
    data += ET.tostring(root, encoding="utf-8") + b"\n"
    destination = out_dir / "timeline.xml"
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=out_dir, prefix=".timeline-", suffix=".xml",
                                         delete=False) as handle:
            temporary = handle.name
            handle.write(data)
        os.replace(temporary, destination)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True,
                        help="Export directory containing resolved-spec.json and resolve/ media")
    arguments = parser.parse_args()
    out_dir = arguments.out.expanduser().resolve()
    try:
        with (out_dir / "resolved-spec.json").open(encoding="utf-8") as handle:
            spec = json.load(handle)
        destination = write_handoff(spec, out_dir)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"handoff: {error}\n")
    print(f"Rebuilt {destination} using media paths on this computer.")
    print("Import timeline.xml and captions.srt in Resolve; application import is not verified here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
