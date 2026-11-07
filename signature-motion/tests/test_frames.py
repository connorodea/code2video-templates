"""Behavior checks for timeline seeking and supported frame formats."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.scenes import render_frame


class FrameBehavior(unittest.TestCase):
    def configs(self):
        return [json.loads(p.read_text()) for p in sorted((ROOT / "examples").glob("*.json"))]

    def test_catalog_has_six_renderable_examples(self):
        configs = self.configs()
        self.assertEqual(len(configs), 6)
        for config in configs:
            for width, height in [(270, 480), (480, 270), (320, 320)]:
                request = {**config, "width": width, "height": height}
                for frame in [0, round(config["fps"] * config["duration"] * .6),
                              round(config["fps"] * config["duration"]) - 1]:
                    with self.subTest(template=config["template"], shape=(width, height), frame=frame):
                        image = render_frame(request, frame)
                        self.assertEqual(image.size, (width, height))
                        self.assertEqual(image.mode, "RGB")

    def test_seeking_out_of_order_preserves_the_frame(self):
        for config in self.configs():
            request = {**config, "width": 270, "height": 480}
            frame = round(config["fps"] * config["duration"] * .6)
            with self.subTest(template=config["template"]):
                expected = render_frame(request, frame).tobytes()
                first = render_frame(request, 0).tobytes()
                render_frame(request, frame // 2)
                self.assertEqual(render_frame(request, frame).tobytes(), expected)
                self.assertNotEqual(first, expected, "The template must actually animate")

    def test_frame_bounds_are_half_open(self):
        config = self.configs()[0]
        config.update(width=270, height=480)
        for invalid in [-1, round(config["fps"] * config["duration"]), 1.5, True]:
            with self.subTest(frame=invalid), self.assertRaises(ValueError):
                render_frame(config, invalid)


if __name__ == "__main__":
    unittest.main()
