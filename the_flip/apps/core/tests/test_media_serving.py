"""Tests for the serve_media view that serves user-uploaded files."""

import shutil
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings, tag

from the_flip.apps.core.test_utils import SuppressRequestLogsMixin


@tag("views")
@override_settings(MEDIA_URL="/media/")
class ServeMediaViewTests(SuppressRequestLogsMixin, TestCase):
    """Tests for the serve_media view that serves user-uploaded files."""

    def setUp(self):
        """Create a temporary directory with test files."""
        self.temp_dir = tempfile.mkdtemp()
        self.media_root = Path(self.temp_dir)

        # Create test files
        self.test_image = self.media_root / "test-image.jpg"
        self.test_image.write_bytes(b"\xff\xd8\xff\xe0")  # JPEG magic bytes

        self.test_video = self.media_root / "test-video.mp4"
        self.test_video.write_bytes(b"\x00\x00\x00\x18ftypmp42")

        # Create a subdirectory with a file
        subdir = self.media_root / "uploads"
        subdir.mkdir()
        self.nested_file = subdir / "nested.txt"
        self.nested_file.write_text("nested content")

    def tearDown(self):
        """Clean up temporary files."""
        shutil.rmtree(self.temp_dir)

    def test_serves_file_with_correct_content_type(self):
        """Valid file returns 200 with correct Content-Type."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/test-image.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")

    def test_serves_file_with_cache_control_header(self):
        """Media files include immutable Cache-Control header for 1 year."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/test-image.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "public, max-age=31536000, immutable")

    def test_serves_file_with_content_length(self):
        """Response includes Content-Length header."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/test-image.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Length"], "4")  # 4 bytes of JPEG magic

    def test_serves_nested_file(self):
        """Files in subdirectories are served correctly."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/uploads/nested.txt")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")

    def test_serves_video_with_correct_content_type(self):
        """Video files return correct Content-Type."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/test-video.mp4")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "video/mp4")

    def test_missing_file_returns_404(self):
        """Non-existent file returns 404."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/nonexistent.jpg")

        self.assertEqual(response.status_code, 404)

    def test_directory_traversal_blocked(self):
        """Path traversal attempts return 404."""
        with override_settings(MEDIA_ROOT=self.media_root):
            # Attempt to escape MEDIA_ROOT
            response = self.client.get("/media/../../../etc/passwd")

        self.assertEqual(response.status_code, 404)

    def test_directory_traversal_encoded_blocked(self):
        """URL-encoded path traversal attempts return 404."""
        with override_settings(MEDIA_ROOT=self.media_root):
            # %2e = '.', %2f = '/'
            response = self.client.get("/media/%2e%2e/%2e%2e/etc/passwd")

        self.assertEqual(response.status_code, 404)

    def test_directory_returns_404(self):
        """Requesting a directory (not a file) returns 404."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/uploads/")

        self.assertEqual(response.status_code, 404)

    def test_empty_path_returns_404(self):
        """Requesting /media/ with no file path returns 404."""
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/")

        self.assertEqual(response.status_code, 404)
