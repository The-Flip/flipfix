"""Environment and dependency checks for maintenance app."""

import shutil
import subprocess

from django.test import TestCase, tag


@tag("integration")
class FFmpegAvailabilityTest(TestCase):
    """Tests that verify video transcoding dependencies are available."""

    def test_ffmpeg_available_on_path(self):
        """Verify ffmpeg is installed and returns version info."""
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not found on PATH (video upload/transcode will fail)")
        result = subprocess.run(
            ["ffmpeg", "-version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertIn("ffmpeg version", (result.stdout or "").lower())

    def test_ffprobe_available_on_path(self):
        """Verify ffprobe is installed and returns version info."""
        if not shutil.which("ffprobe"):
            self.skipTest("ffprobe not found on PATH (video upload/transcode will fail)")
        result = subprocess.run(
            ["ffprobe", "-version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertIn("ffprobe version", (result.stdout or "").lower())
