"""Regression checks for word timing, local audio offsets, and exact PCM exports."""
import copy
import ctypes.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio import SAMPLE_RATE, prepare_audio
from captions import chunk_words, load_words, validate_words, write_srt


class CaptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.words = [{"word": "hello", "punctuated_word": "Hello,", "start": .1, "end": .3},
                      {"word": "world", "punctuated_word": "world!", "start": .3, "end": .7}]

    def tearDown(self):
        self.temp.cleanup()

    def load_json(self, data, **kwargs):
        path = self.directory / "words.json"
        path.write_text(json.dumps(data))
        return load_words(path, **kwargs)

    def test_deepgram_channel_punctuation_and_offset(self):
        response = {"results": {"channels": [{"alternatives": [{"words": self.words}]},
                    {"alternatives": [{"words": [{"word": "Other", "start": .2, "end": .5}]}]}]}}
        words, source = self.load_json(response, offset_seconds=1, duration_seconds=2)
        self.assertEqual(source, "deepgram-word-timestamps")
        self.assertEqual(words[0], {"word": "Hello,", "start": 1.1, "end": 1.3})
        self.assertEqual(self.load_json(response, channel=1)[0][0]["word"], "Other")
        with self.assertRaises(ValueError):
            self.load_json(response, channel=2)

    def test_generic_words_and_segments(self):
        for data in (self.words, {"words": self.words}, {"segments": [{"words": self.words}]}):
            self.assertEqual(self.load_json(data)[0][1]["word"], "world!")
        words, source = self.load_json({"segments": [{"text": "one two", "start": 1, "end": 2}]})
        self.assertEqual(words[0]["end"], 1.5)
        self.assertIn("approximate", source)

    def test_srt_multiline_markup_and_approximation(self):
        path = self.directory / "captions.srt"
        path.write_bytes(b'\xef\xbb\xbf1\r\n00:00:01,000 --> 00:00:03,000\r\n<i>Hello</i>\r\n<font color="#fff"><b>world.</b></font>\r\n')
        words, source = load_words(path)
        self.assertIn("approximate", source)
        self.assertEqual(words, [{"word": "Hello", "start": 1., "end": 2.},
                                 {"word": "world.", "start": 2., "end": 3.}])

    def test_reject_bad_timestamps(self):
        for start, end in ((-1, 1), (0, 0), (1, .5), (False, 1), (0, float("inf")), (float("nan"), 1), ("0", 1)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                validate_words([{"word": "x", "start": start, "end": end}])
        for words in ([], [{"word": "", "start": 0, "end": 1}],
                      [{"word": "x", "start": 0, "end": 1}, {"word": "y", "start": .9, "end": 2}]):
            with self.assertRaises(ValueError):
                validate_words(words)
        with self.assertRaises(ValueError):
            validate_words(self.words, .6)

    def test_bad_format_offsets_and_segment_text(self):
        for kwargs in ({"offset_seconds": -1}, {"offset_seconds": float("nan")}, {"channel": True}, {"format": "other"}):
            with self.assertRaises(ValueError):
                self.load_json(self.words, **kwargs)
        with self.assertRaises(ValueError):
            self.load_json({"segments": [{"text": 123, "start": 0, "end": 1}]})

    def test_chunking_respects_count_gap_and_sentence(self):
        words = [{"word": token, "start": i * .2, "end": (i + 1) * .2}
                 for i, token in enumerate(["One", "two.", "Three", "four", "five"])]
        words.append({"word": "Six", "start": 2, "end": 2.5})
        chunks = chunk_words(words, max_words=2)
        self.assertEqual([c["text"] for c in chunks], ["One two.", "Three four", "five", "Six"])
        self.assertEqual(chunks[-1]["start"], 2)

    def test_srt_export_keeps_real_cue_bounds(self):
        path = self.directory / "export.srt"
        write_srt(chunk_words(self.words), path)
        self.assertIn("00:00:00,100 --> 00:00:00,700", path.read_text())
        self.assertIn("Hello, world!", path.read_text())
        with self.assertRaises(ValueError):
            write_srt([{"text": "too short", "start": 0, "end": .0001}], path)


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for local audio integration")
class AudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.input_samples = 12000
        self.source = self.directory / "input.wav"
        t = np.arange(self.input_samples) / SAMPLE_RATE
        source = np.rint(np.sin(2 * np.pi * 220 * t) * 5000).astype("<i2")
        with wave.open(str(self.source), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(SAMPLE_RATE)
            stream.writeframes(source.tobytes())
        (self.directory / "words.json").write_text(json.dumps({"results": {"channels": [
            {"alternatives": [{"words": [{"word": "tone", "start": .02, "end": .20}]}]}]}}))
        self.spec = {"video": {"fps": 30, "duration_frames": 90}, "project": {"seed": 7, "demo": True},
                     "audio": {"sample_rate": 48000, "voice_gain": .85, "music_gain": .11, "sfx_gain": .32, "bpm": 100},
                     "narration": {"mode": "file", "path": "input.wav", "captions_path": "words.json",
                                   "captions_format": "deepgram", "offset_seconds": .5},
                     "scenes": [{"id": "a", "start_frame": 0, "transition_in": "cut", "transition_frames": 0},
                                {"id": "b", "start_frame": 30, "transition_in": "wipe", "transition_frames": 12}]}

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, spec=None, name="out"):
        return prepare_audio(spec or self.spec, self.directory, self.directory / name)

    def test_exact_format_audio_offset_and_sync_events(self):
        result = self.prepare()
        self.assertEqual(result["words"][0]["start"], .52)
        self.assertEqual(result["duration_samples"], 144000)
        for name, path in result["stems"].items():
            with wave.open(path, "rb") as stream:
                self.assertEqual((stream.getframerate(), stream.getnchannels(), stream.getsampwidth(), stream.getnframes()),
                                 (48000, 2, 2, 144000))
                pcm = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").reshape(-1, 2)
                self.assertLess(np.abs(pcm.astype(int)).max(), 32767)
                if name == "narration":
                    self.assertTrue(np.all(pcm[:24000] == 0))
                    self.assertGreater(np.abs(pcm[24000:36000].astype(int)).max(), 1000)
                    self.assertTrue(np.all(pcm[36000:] == 0))
        for event in result["sync_events"]:
            self.assertEqual(event["sample"], round(event["frame"] * SAMPLE_RATE / 30))

    def test_audio_overshoot_is_not_silently_truncated(self):
        spec = copy.deepcopy(self.spec)
        spec["narration"]["offset_seconds"] = 2.9
        with self.assertRaisesRegex(ValueError, "no audio was truncated"):
            self.prepare(spec)

    def test_caption_cannot_extend_past_source_audio(self):
        (self.directory / "words.json").write_text(json.dumps([{"word": "late", "start": .3, "end": .4}]))
        self.spec["narration"]["captions_format"] = "words"
        with self.assertRaisesRegex(ValueError, "beyond the supplied narration audio"):
            self.prepare()

    def test_procedural_assets_are_reproducible(self):
        first = self.prepare(name="one")
        second = self.prepare(name="two")
        for stem in first["stems"]:
            self.assertEqual(Path(first["stems"][stem]).read_bytes(), Path(second["stems"][stem]).read_bytes())

    @unittest.skipUnless(ctypes.util.find_library("flite_cmu_us_slt"), "Native Flite SLT voice is required")
    def test_native_speech_and_word_boundaries(self):
        spec = copy.deepcopy(self.spec)
        spec["narration"] = {"mode": "synthetic", "voice": "slt", "lines": [{"start_frame": 0, "text": "Every route starts with a question."}]}
        result = self.prepare(spec)
        self.assertEqual(result["timing_source"], "flite-native-word-boundaries")
        self.assertEqual(" ".join(word["word"] for word in result["words"]), spec["narration"]["lines"][0]["text"])
        self.assertGreater(result["words"][0]["start"], 0)
        self.assertLess(result["words"][-1]["end"], 3)
        spec["narration"]["lines"].append({"start_frame": 1, "text": "Overlap."})
        with self.assertRaisesRegex(ValueError, "overlaps"):
            self.prepare(spec, name="overlap")


if __name__ == "__main__":
    unittest.main()
