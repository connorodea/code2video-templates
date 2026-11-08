"""Contract tests for XML timing, channel routing, and offline relocation.

Fixture media are placeholders: actual media codecs and duration are checked by
qa.py during a render. These tests do not claim Resolve application import.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from handoff import MEDIA, write_handoff  # noqa: E402


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.out = Path(self.temporary.name) / "Export space #100% Ω"
        self.out.mkdir()
        for relative in MEDIA.values():
            path = self.out / relative
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b"fixture media; codec checks belong to render QA")
        self.spec = {
            "project": {"title": "GTA <field> & notes"},
            "video": {"width": 1920, "height": 1080, "fps": 30, "duration_frames": 720},
            "scenes": [
                {"id": f"scene-{i + 1}", "start_frame": i * 180, "duration_frames": 180}
                for i in range(4)
            ],
        }

    def document(self):
        path = write_handoff(self.spec, self.out)
        self.assertEqual(path, self.out / "timeline.xml")
        return ET.parse(path).getroot()

    def test_scene_cuts_preserve_master_time_and_alpha(self):
        root = self.document()
        self.assertEqual(root.tag, "xmeml")
        self.assertEqual(root.get("version"), "5")
        sequence = root.find("sequence")
        self.assertEqual(sequence.findtext("name"), self.spec["project"]["title"])
        self.assertEqual(sequence.findtext("duration"), "720")
        self.assertEqual(sequence.findtext("timecode/frame"), "0")
        self.assertEqual(sequence.findtext("rate/timebase"), "30")
        self.assertEqual(sequence.findtext("rate/ntsc"), "FALSE")
        tracks = sequence.findall("media/video/track")
        self.assertEqual(len(tracks), 2)
        for layer, track in zip(("clean", "graphics"), tracks):
            clips = track.findall("clipitem")
            self.assertEqual(len(clips), 4)
            for scene, clip in zip(self.spec["scenes"], clips):
                start = scene["start_frame"]
                end = start + scene["duration_frames"]
                self.assertEqual(tuple(int(clip.findtext(tag)) for tag in ("start", "end", "in", "out")),
                                 (start, end, start, end))
                self.assertEqual(clip.findtext("alphatype"), "straight" if layer == "graphics" else "none")
                self.assertEqual(clip.find("file").get("id"), f"file-{layer}")
            self.assertEqual(track.findall("transitionitem"), [])

    def test_unique_definitions_and_percent_encoded_existing_file_urls(self):
        root = self.document()
        definitions = [element for element in root.iter() if element.get("id") and len(element)]
        ids = [element.get("id") for element in definitions]
        self.assertEqual(len(ids), len(set(ids)))
        file_definitions = root.findall(".//file[pathurl]")
        self.assertEqual(len(file_definitions), 5)
        by_id = {element.get("id"): element for element in file_definitions}
        for key, relative in MEDIA.items():
            element = by_id[f"file-{key}"]
            url = element.findtext("pathurl")
            self.assertEqual(url, (self.out / relative).resolve().as_uri())
            self.assertNotIn(" ", url)
            self.assertIn("%23", url)
            self.assertIn("%25", url)
            self.assertIn("%CE%A9", url)
            self.assertTrue(Path(unquote(urlsplit(url).path)).is_file())
            self.assertEqual(element.findtext("duration"), "720")
        for element in root.findall(".//file"):
            self.assertIn(element.get("id"), by_id)
        self.assertIsNone(root.find(".//file[@id='file-mix']"))

    def test_three_stereo_stems_route_six_channels_without_cross_links(self):
        root = self.document()
        audio = root.find("sequence/media/audio")
        tracks = audio.findall("track")
        self.assertEqual(len(tracks), 6)
        self.assertEqual(audio.findtext("outputs/group/numchannels"), "2")
        for index, track in enumerate(tracks):
            stem = ("narration", "music", "sfx")[index // 2]
            channel = index % 2 + 1
            clip = track.find("clipitem")
            self.assertEqual(clip.findtext("sourcetrack/trackindex"), str(channel))
            self.assertEqual(track.findtext("outputchannelindex"), str(channel))
            self.assertEqual(tuple(int(clip.findtext(tag)) for tag in ("start", "end", "in", "out")),
                             (0, 720, 0, 720))
            self.assertEqual({link.findtext("linkclipref") for link in clip.findall("link")},
                             {f"clip-{stem}-1", f"clip-{stem}-2"})
            self.assertEqual({link.findtext("groupindex") for link in clip.findall("link")}, {"1"})
            self.assertEqual({int(link.findtext("trackindex")) for link in clip.findall("link")},
                             {2 * (index // 2) + 1, 2 * (index // 2) + 2})
        for file in (item for item in root.findall(".//file") if item.find("media/audio") is not None):
            self.assertEqual(file.findtext("media/audio/channelcount"), "2")
            self.assertEqual(file.findtext("media/audio/samplecharacteristics/samplerate"), "48000")
            self.assertEqual(file.findtext("media/audio/samplecharacteristics/depth"), "16")

    def test_relocation_cli_works_with_standard_library_only(self):
        self.document()
        (self.out / "resolved-spec.json").write_text(json.dumps(self.spec), encoding="utf-8")
        relocated = Path(self.temporary.name) / "moved package"
        shutil.copytree(self.out, relocated)
        standalone = relocated / "handoff.py"
        shutil.copyfile(HERE / "handoff.py", standalone)
        # -I ignores PYTHONPATH; -S skips site-packages. This copy must not
        # import rendering modules, Pillow, NumPy, or jsonschema.
        result = subprocess.run([sys.executable, "-I", "-S", str(standalone), "--out", str(relocated)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        urls = [element.text for element in ET.parse(relocated / "timeline.xml").findall(".//pathurl")]
        self.assertEqual(set(urls), {(relocated / relative).resolve().as_uri() for relative in MEDIA.values()})
        self.assertNotIn(self.out.as_uri(), "\n".join(urls))

    def test_failed_rebuild_preserves_existing_xml(self):
        path = write_handoff(self.spec, self.out)
        original = path.read_bytes()
        (self.out / MEDIA["graphics"]).unlink()
        with self.assertRaisesRegex(FileNotFoundError, "graphics.mov"):
            write_handoff(self.spec, self.out)
        self.assertEqual(path.read_bytes(), original)

    def test_rejects_timeline_gaps_duplicates_and_fractional_frames(self):
        for case in ("gap", "duplicate", "fractional", "duration", "rate"):
            with self.subTest(case=case):
                spec = copy.deepcopy(self.spec)
                if case == "gap":
                    spec["scenes"][1]["start_frame"] += 1
                elif case == "duplicate":
                    spec["scenes"][1]["id"] = spec["scenes"][0]["id"]
                elif case == "fractional":
                    spec["scenes"][0]["duration_frames"] = 180.5
                elif case == "duration":
                    spec["video"]["duration_frames"] += 1
                else:
                    spec["video"]["fps"] = 29.97
                with self.assertRaises(ValueError):
                    write_handoff(spec, self.out)


if __name__ == "__main__":
    unittest.main()
