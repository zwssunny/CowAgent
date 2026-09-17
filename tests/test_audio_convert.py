# encoding:utf-8
"""Regression tests for the silk branch of voice.audio_convert.any_to_mp3.

It used to decode onto the caller's own file and then re-encode from a path that
had not been written yet: the conversion always failed, and the voice file the
caller fell back to had already been overwritten with wav bytes.
"""
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import voice.audio_convert as audio_convert


class _FakeSegment:
    """Minimal stand-in for pydub's AudioSegment."""

    def export(self, out_path, format=None):
        with open(out_path, "wb") as f:
            f.write(b"mp3-bytes")


class TestAnyToMp3Silk(unittest.TestCase):
    SILK_BYTES = b"SILK" + b"\x02\x00" * 8
    DECODED_WAV = b"RIFF" + b"\x00" * 44

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="audio-convert-")
        self.addCleanup(self._tmp.cleanup)
        self.src = os.path.join(self._tmp.name, "wx_1.silk")
        self.dst = os.path.join(self._tmp.name, "wx_1.mp3")
        with open(self.src, "wb") as f:
            f.write(self.SILK_BYTES)
        # pydub is an optional extra (requirements-optional.txt).
        guard = patch.object(audio_convert, "_pydub_available", True)
        guard.start()
        self.addCleanup(guard.stop)

    def _convert(self):
        """Convert and report what AudioSegment.from_file was handed.

        Each entry is (path, existed): a reader can only open a path that is
        already on disk. pysilk is an optional native dependency, so its
        decoder is stubbed -- sil_to_wav itself still does real file I/O.
        """
        reads = []

        def from_file(path, *args, **kwargs):
            reads.append((path, os.path.exists(path)))
            if not os.path.exists(path):
                raise FileNotFoundError(path)
            return _FakeSegment()

        pysilk = SimpleNamespace(
            decode_file=lambda path, to_wav=False, sample_rate=None: self.DECODED_WAV
        )
        segment = SimpleNamespace(from_file=from_file)
        with patch.object(audio_convert, "pysilk", pysilk, create=True), patch.object(
            audio_convert, "AudioSegment", segment
        ):
            audio_convert.any_to_mp3(self.src, self.dst)
        return reads

    def test_source_voice_file_is_left_untouched(self):
        self._convert()
        with open(self.src, "rb") as f:
            self.assertEqual(f.read(), self.SILK_BYTES)

    def test_decoded_audio_is_read_from_a_file_that_exists(self):
        reads = self._convert()
        self.assertEqual(len(reads), 1)
        path, existed = reads[0]
        self.assertTrue(existed, f"{path} was read before it existed")
        self.assertTrue(path.endswith(".wav"), path)

    def test_mp3_is_written_and_the_scratch_wav_is_removed(self):
        reads = self._convert()
        with open(self.dst, "rb") as f:
            self.assertEqual(f.read(), b"mp3-bytes")
        self.assertFalse(os.path.exists(reads[0][0]), "scratch wav left behind")
