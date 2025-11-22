"""Check FFmpeg/FFprobe availability."""
from __future__ import annotations

import subprocess

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Check FFmpeg and FFprobe availability"

    def handle(self, *args, **options):
        self._check_binary("ffmpeg")
        self._check_binary("ffprobe")

    def _check_binary(self, binary: str):
        try:
            result = subprocess.run(
                [binary, "-version"],
                capture_output=True,
                text=True,
                check=True,
            )
            first_line = (result.stdout or "").splitlines()[0] if result.stdout else ""
            self.stdout.write(self.style.SUCCESS(f"✓ {binary} available: {first_line}"))
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"✗ {binary} not found on PATH"))
        except subprocess.CalledProcessError as exc:  # pragma: no cover
            self.stdout.write(self.style.ERROR(f"✗ {binary} returned error: {exc}"))
