import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spec import local_path, validate_spec


class SceneContractTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT / "examples" / "pilot.json").read_text())

    def test_demo_valid_and_exactly_720_frames(self):
        validate_spec(self.spec, ROOT / "examples")
        self.assertEqual(sum(s["duration_frames"] for s in self.spec["scenes"]), 720)

    def test_rejects_gap_and_overlap(self):
        for change in (-1, 1):
            with self.subTest(change=change):
                spec = copy.deepcopy(self.spec)
                spec["scenes"][1]["start_frame"] += change
                with self.assertRaisesRegex(ValueError, "gaps and overlaps"):
                    validate_spec(spec, ROOT)

    def test_rejects_unknown_and_nonfinite_fields(self):
        for field, value in (("accent", "red"), ("safe_margin", float("nan")), ("shell_command", "anything")):
            with self.subTest(field=field):
                spec = copy.deepcopy(self.spec)
                spec["style"][field] = value
                with self.assertRaises(ValueError):
                    validate_spec(spec, ROOT)

    def test_mismatched_total_is_not_silently_padded(self):
        self.spec["video"]["duration_frames"] += 1
        with self.assertRaisesRegex(ValueError, "Scenes cover"):
            validate_spec(self.spec, ROOT)

    def test_synthetic_speech_requires_demo_label(self):
        self.spec["project"]["demo"] = False
        with self.assertRaisesRegex(ValueError, "demonstration"):
            validate_spec(self.spec, ROOT)

    def test_transition_cannot_extend_sequence(self):
        self.spec["scenes"][1]["transition_frames"] = 100
        with self.assertRaisesRegex(ValueError, "half its duration"):
            validate_spec(self.spec, ROOT)

    def test_external_media_needs_attribution(self):
        self.spec["scenes"][0]["background"] = {"kind": "video", "path": "demo.mp4"}
        with self.assertRaisesRegex(ValueError, "required"):
            validate_spec(self.spec, ROOT, check_files=False)

    def test_network_protocols_are_not_asset_paths(self):
        for value in ("https://example.com/video.mp4", "pipe:0", "concat:a|b", "data:video/mp4;base64,abcd"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "local file"):
                local_path(value, ROOT)

    def test_duplicate_scene_ids_rejected(self):
        self.spec["scenes"][1]["id"] = self.spec["scenes"][0]["id"]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_spec(self.spec, ROOT)


if __name__ == "__main__":
    unittest.main()
