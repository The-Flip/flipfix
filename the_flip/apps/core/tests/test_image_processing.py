"""Tests for image processing utilities."""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, tag
from PIL import Image

from the_flip.apps.core.image_processing import (
    MAX_IMAGE_DIMENSION,
    THUMB_IMAGE_DIMENSION,
    resize_image_file,
)


def create_test_image(width: int, height: int, format: str = "PNG", mode: str = "RGB") -> bytes:
    """Create a test image of the given dimensions and return as bytes."""
    image = Image.new(mode, (width, height), color="red")
    buffer = BytesIO()
    image.save(buffer, format=format)
    return buffer.getvalue()


@tag("unit")
class ResizeImageFileTests(TestCase):
    """Tests for the resize_image_file function."""

    def test_passthrough_for_non_image_content_type(self):
        """Non-image files are returned unchanged."""
        pdf_content = b"%PDF-1.4 fake pdf content"
        uploaded = SimpleUploadedFile("doc.pdf", pdf_content, content_type="application/pdf")

        result = resize_image_file(uploaded)

        # Should be the same object, not a new file
        self.assertIs(result, uploaded)

    def test_passthrough_for_unrecognized_binary(self):
        """Binary files that PIL can't identify are returned unchanged."""
        binary_content = b"\x00\x01\x02\x03 random bytes"
        uploaded = SimpleUploadedFile(
            "data.bin", binary_content, content_type="application/octet-stream"
        )

        result = resize_image_file(uploaded)

        self.assertIs(result, uploaded)

    def test_small_png_preserves_format_and_transparency(self):
        """Small PNG with transparency stays PNG (not converted to JPEG)."""
        small_image = create_test_image(100, 100, format="PNG", mode="RGBA")
        uploaded = SimpleUploadedFile("small.png", small_image, content_type="image/png")

        result = resize_image_file(uploaded)

        # Should remain PNG, preserving transparency capability
        self.assertEqual(result.content_type, "image/png")

    def test_large_image_is_resized(self):
        """Images larger than MAX_IMAGE_DIMENSION are downsized."""
        # Create an image larger than the max dimension
        large_image = create_test_image(3000, 2000, format="JPEG")
        uploaded = SimpleUploadedFile("large.jpg", large_image, content_type="image/jpeg")

        result = resize_image_file(uploaded)

        # Should be a new file, not the original
        self.assertIsNot(result, uploaded)

        # Verify the result is smaller
        result.seek(0)
        img = Image.open(result)
        self.assertLessEqual(max(img.size), MAX_IMAGE_DIMENSION)

    def test_custom_max_dimension(self):
        """Custom max_dimension is respected."""
        image_data = create_test_image(1000, 800, format="JPEG")
        uploaded = SimpleUploadedFile("medium.jpg", image_data, content_type="image/jpeg")

        result = resize_image_file(uploaded, max_dimension=500)

        result.seek(0)
        img = Image.open(result)
        self.assertLessEqual(max(img.size), 500)

    def test_thumbnail_dimension_constant(self):
        """THUMB_IMAGE_DIMENSION can be used for thumbnail generation."""
        image_data = create_test_image(1200, 900, format="JPEG")
        uploaded = SimpleUploadedFile("photo.jpg", image_data, content_type="image/jpeg")

        result = resize_image_file(uploaded, max_dimension=THUMB_IMAGE_DIMENSION)

        result.seek(0)
        img = Image.open(result)
        self.assertLessEqual(max(img.size), THUMB_IMAGE_DIMENSION)

    def test_png_with_transparency_stays_png(self):
        """PNG images with alpha channel remain PNG (not converted to JPEG)."""
        rgba_image = create_test_image(3000, 2000, format="PNG", mode="RGBA")
        uploaded = SimpleUploadedFile("transparent.png", rgba_image, content_type="image/png")

        result = resize_image_file(uploaded)

        self.assertEqual(result.content_type, "image/png")
        self.assertTrue(result.name.endswith(".png"))

    def test_non_jpeg_non_png_converted_to_jpeg(self):
        """Non-JPEG/PNG formats (like BMP, GIF) are converted to JPEG."""
        # Create a BMP image
        bmp_image = create_test_image(100, 100, format="BMP")
        uploaded = SimpleUploadedFile("image.bmp", bmp_image, content_type="image/bmp")

        result = resize_image_file(uploaded)

        # BMP triggers format conversion even without resize
        self.assertEqual(result.content_type, "image/jpeg")
        self.assertTrue(result.name.endswith(".jpg"))

    def test_heic_extension_triggers_processing(self):
        """Files with .heic extension are processed even with generic content type.

        This tests the fallback for when content_type is not set correctly.
        Note: Actual HEIC decoding requires pillow-heif, so we just verify
        the function handles the file gracefully.
        """
        # We can't create actual HEIC without pillow-heif, but we can test
        # that the function doesn't reject HEIC extension files outright
        fake_heic = b"fake heic content"
        uploaded = SimpleUploadedFile(
            "photo.heic", fake_heic, content_type="application/octet-stream"
        )

        # Should not raise, should return the file (unchanged since it's not valid HEIC)
        result = resize_image_file(uploaded)
        self.assertIs(result, uploaded)

    def test_max_dimension_none_skips_resize_but_converts_format(self):
        """Passing max_dimension=None skips resizing but still converts format."""
        # BMP should be converted to JPEG even without resizing
        bmp_image = create_test_image(100, 100, format="BMP")
        uploaded = SimpleUploadedFile("image.bmp", bmp_image, content_type="image/bmp")

        result = resize_image_file(uploaded, max_dimension=None)

        # Should still convert to JPEG
        self.assertEqual(result.content_type, "image/jpeg")

    def test_preserves_aspect_ratio(self):
        """Resizing preserves the original aspect ratio."""
        # Create a wide image
        wide_image = create_test_image(4000, 1000, format="JPEG")
        uploaded = SimpleUploadedFile("wide.jpg", wide_image, content_type="image/jpeg")

        result = resize_image_file(uploaded)

        result.seek(0)
        img = Image.open(result)
        width, height = img.size

        # Original aspect ratio is 4:1
        original_ratio = 4000 / 1000
        result_ratio = width / height
        self.assertAlmostEqual(original_ratio, result_ratio, places=1)

    def test_result_is_inmemoryuploadedfile(self):
        """Processed files are returned as InMemoryUploadedFile."""
        large_image = create_test_image(3000, 2000, format="JPEG")
        uploaded = SimpleUploadedFile("large.jpg", large_image, content_type="image/jpeg")

        result = resize_image_file(uploaded)

        from django.core.files.uploadedfile import InMemoryUploadedFile

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertIsNotNone(result.size)
        self.assertGreater(result.size, 0)
