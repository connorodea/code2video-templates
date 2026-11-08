import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from media import Encoder, probe, run, check_sources


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires local FFmpeg")
class RealEncoderTests(unittest.TestCase):
    def test_prores_color_alpha_and_frame_count_survive_encoding(self):
        video = {"width": 320, "height": 320, "fps": 30}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "alpha.mov"
            image = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((60, 60, 250, 250), fill="#66d9cf")
            encoder = Encoder(path, video, "graphics")
            for _ in range(3):
                encoder.write(image)
            encoder.close()
            stream = next(s for s in probe(path, count_frames=True)["streams"] if s["codec_type"] == "video")
            self.assertEqual(stream["codec_name"], "prores")
            self.assertEqual(stream["profile"], "4444")
            self.assertEqual(int(stream["nb_read_frames"]), 3)
            for field in ("color_space", "color_transfer", "color_primaries"):
                self.assertEqual(stream[field], "bt709")
            alpha = np.frombuffer(run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", "alphaextract,format=gray", "-frames:v", "1", "-f", "rawvideo", "pipe:1"]).stdout, dtype=np.uint8)
            self.assertEqual(int(alpha.min()), 0)
            self.assertEqual(int(alpha.max()), 255)

    def test_insufficient_footage_fails_instead_of_looping(self):
        video = {"width": 320, "height": 320, "fps": 30}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.mp4"
            encoder = Encoder(path, video, "review")
            for _ in range(3):
                encoder.write(Image.new("RGB", (320, 320), "#102020"))
            encoder.close()
            spec = {"video": video, "scenes": [{"id": "source", "duration_frames": 30,
                    "background": {"kind": "video", "path": str(path), "in_seconds": 0}}]}
            with self.assertRaisesRegex(ValueError, "no automatic looping"):
                check_sources(spec, Path(directory))


if __name__ == "__main__":
    unittest.main()
