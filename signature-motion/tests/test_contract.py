"""Behavioral checks at the agent/renderer boundary; no encoder required."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.validation import ConfigError, config_hash, load_config, preview_config, validate_config


def example(name="type-impact"):
    return json.loads((ROOT / "examples" / f"{name}.json").read_text())


class InputContract(unittest.TestCase):
    def test_registry_examples_validate_without_mutation(self):
        registry = json.loads((ROOT / "templates.json").read_text())
        self.assertEqual(len(registry["templates"]), 6)
        for template in registry["templates"]:
            path = ROOT / template["example"]
            raw, runtime = load_config(path)
            with self.subTest(template=template["id"]):
                self.assertEqual(raw["template"], template["id"])
                self.assertEqual(raw, runtime)
                self.assertIsNot(raw, runtime)

    def test_invalid_timing_and_dimensions_fail_before_rendering(self):
        for changes in [
            {"fps": True}, {"fps": 29.97}, {"duration": 6.01},
            {"duration": float("inf")}, {"duration": 10 ** 500},
            {"width": 1081}, {"width": 1000}, {"width": 2, "height": 2},
            {"width": 1920, "height": 1920}, {"seed": -1},
        ]:
            with self.subTest(changes=str(changes)), self.assertRaises(ConfigError):
                validate_config({**example(), **changes})

    def test_unknown_fields_and_overlong_copy_are_rejected(self):
        configurations = []
        unknown = example()
        unknown["unexpected"] = "ignored fields could hide agent mistakes"
        configurations.append(unknown)
        long_copy = example()
        long_copy["content"]["headline"][0] = "W" * 19
        configurations.append(long_copy)
        blank = example()
        blank["brand"] = "   "
        configurations.append(blank)
        for config in configurations:
            with self.subTest(config=config), self.assertRaises(ConfigError):
                validate_config(config)

    def test_production_evidence_requires_a_source_url(self):
        for template in ["redline", "signal"]:
            config = example(template)
            config["demo"] = False
            with self.subTest(template=template):
                with self.assertRaises(ConfigError):
                    validate_config(config)
                config["content"]["source_url"] = "https://example.org/research"
                validate_config(config)
                for invalid in ["https://user:secret@example.org", "javascript:alert(1)", "https://bad host"]:
                    config["content"]["source_url"] = invalid
                    with self.assertRaises(ConfigError):
                        validate_config(config)

    def test_numeric_series_rejects_nonfinite_and_out_of_range_values(self):
        for value in [True, -1, float("nan"), float("inf"), 1e16, 10 ** 500]:
            config = example("signal")
            config["content"]["series"][0]["value"] = value
            with self.subTest(value=str(value)), self.assertRaises(ConfigError):
                validate_config(config)

    def test_preview_retains_aspect_and_minimum_dimensions(self):
        for width, height in [(1080, 1920), (1920, 1080), (1080, 1080)]:
            original = {**example(), "width": width, "height": height}
            for scale in [.0001, .33, .5, 1]:
                preview = preview_config(original, scale)
                self.assertGreaterEqual(min(preview["width"], preview["height"]), 144)
                self.assertEqual(preview["width"] * height, preview["height"] * width)
                validate_config(preview)
            self.assertEqual(original["width"], width)

    def test_local_assets_resolve_relative_to_the_config(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            # Decoding belongs to the render boundary; validate needs only readable files.
            for number in range(3):
                (folder / f"asset-{number}.png").write_bytes(b"readable placeholder")
            config = example("prism")
            config["content"]["assets"] = [f"asset-{number}.png" for number in range(3)]
            runtime = validate_config(config, folder)
            self.assertTrue(all(Path(path).is_absolute() for path in runtime["content"]["assets"]))
            self.assertEqual(config["content"]["assets"][0], "asset-0.png")
            for invalid in ["missing.png", "https://example.org/image.png", "data:image/png;base64,eA=="]:
                candidate = copy.deepcopy(config)
                candidate["content"]["assets"][0] = invalid
                with self.assertRaises(ConfigError):
                    validate_config(candidate, folder)

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema_version":1,"schema_version":2}')
            with self.assertRaisesRegex(ConfigError, "duplicate JSON key"):
                load_config(path)

    def test_config_hash_ignores_key_order(self):
        config = example()
        reversed_config = dict(reversed(list(config.items())))
        self.assertEqual(config_hash(config), config_hash(reversed_config))

    def test_cli_validation_works_without_site_packages(self):
        result = subprocess.run([
            sys.executable, "-S", str(ROOT / "render.py"),
            "--config", str(ROOT / "examples" / "type-impact.json"), "--validate"
        ], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["valid"])


if __name__ == "__main__":
    unittest.main()
