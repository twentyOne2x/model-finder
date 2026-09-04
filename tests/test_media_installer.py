import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("media_installer", ROOT / "scripts/install-wow-media.py")
INSTALLER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = INSTALLER
SPEC.loader.exec_module(INSTALLER)


class MediaInstallerTests(unittest.TestCase):
    def test_requires_explicit_acknowledgement_before_download(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "untouched"
            result = subprocess.run([sys.executable, str(ROOT / "scripts/install-wow-media.py"),
                                     "--output-root", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("--accept-third-party-terms", result.stderr)
            self.assertFalse(output.exists())

    def test_sources_are_https_and_checksum_pinned(self):
        for asset in (*INSTALLER.AUDIO_ASSETS, *INSTALLER.CURSOR_ASSETS):
            self.assertTrue(asset.url.startswith("https://"))
            self.assertRegex(asset.source_sha256, r"^[a-f0-9]{64}$")
            self.assertLess(asset.source_size, INSTALLER.MAX_SOURCE_BYTES)
        for asset in INSTALLER.CURSOR_ASSETS:
            self.assertIn(INSTALLER.CRAFTCURSORS_COMMIT, asset.url)

    def test_download_rejects_changed_bytes_before_writing(self):
        asset = INSTALLER.AUDIO_ASSETS[0]
        response = Mock()
        response.headers.get.return_value = str(asset.source_size)
        response.read.return_value = b"x" * asset.source_size
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with tempfile.TemporaryDirectory() as directory, patch.object(INSTALLER, "urlopen", return_value=response):
            destination = Path(directory) / "audio.ogg"
            with self.assertRaisesRegex(INSTALLER.InstallError, "SHA-256 mismatch"):
                INSTALLER.download(asset, destination, 5)
            self.assertFalse(destination.exists())

    def test_oversized_response_is_rejected(self):
        response = Mock()
        response.headers.get.return_value = str(INSTALLER.MAX_SOURCE_BYTES + 1)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with tempfile.TemporaryDirectory() as directory, patch.object(INSTALLER, "urlopen", return_value=response):
            with self.assertRaisesRegex(INSTALLER.InstallError, "oversized"):
                INSTALLER.download(INSTALLER.AUDIO_ASSETS[0], Path(directory) / "x", 5)
            response.read.assert_not_called()

    def test_audio_validation_uses_pcm_not_wav_metadata(self):
        pcm = b"\0\0\0\0" * 10
        asset = INSTALLER.AudioAsset("test.ogg", "https://example.com/test.ogg", "0" * 64,
                                     1, "test.wav", 10, hashlib.sha256(pcm).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "test.wav"
            with wave.open(str(destination), "wb") as audio:
                audio.setnchannels(2)
                audio.setsampwidth(2)
                audio.setframerate(44100)
                audio.writeframes(pcm)
            self.assertTrue(INSTALLER.validate_audio(destination, asset))
            destination.write_bytes(b"not a wave file")
            self.assertFalse(INSTALLER.validate_audio(destination, asset))


if __name__ == "__main__":
    unittest.main()
