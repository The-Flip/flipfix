"""Check HEIC/HEIF support and resize pipeline."""

from __future__ import annotations

from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError

from the_flip.apps.maintenance.utils import resize_image_file


class Command(BaseCommand):
    help = "Diagnose image/HEIC support and the resize pipeline. Optionally pass --file /path/to/image."

    def add_arguments(self, parser):
        parser.add_argument(
            "-f",
            "--file",
            dest="file_path",
            help="Path to an image to open and pass through resize_image_file.",
        )

    def handle(self, *args, **options):
        self._print_library_info()
        file_path = options.get("file_path")
        if file_path:
            self._process_file(Path(file_path))

    # ---- Helpers -----------------------------------------------------
    def _print_library_info(self):
        try:
            import PIL

            self.stdout.write(f"Pillow: {PIL.__version__}")
        except Exception as exc:  # pragma: no cover
            self.stdout.write(self.style.ERROR(f"Could not import Pillow: {exc}"))
            return

        try:
            import pillow_heif
            from pillow_heif import register_heif_opener

            register_heif_opener()
            self.stdout.write(f"pillow-heif: {pillow_heif.__version__} (opener registered)")
        except ImportError:
            self.stdout.write(
                self.style.WARNING("pillow-heif not installed; HEIC may fail to decode.")
            )
        except Exception as exc:  # pragma: no cover
            self.stdout.write(self.style.ERROR(f"pillow-heif import/registration failed: {exc}"))

    def _process_file(self, path: Path):
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        try:
            from PIL import Image

            with path.open("rb") as fh:
                img = Image.open(fh)
                img.load()
                self.stdout.write(
                    f"Opened {path.name}: format={img.format}, mode={img.mode}, size={img.size}"
                )
        except Exception as exc:  # pragma: no cover
            raise CommandError(f"Failed to open {path}: {exc}")

        # Run through resize/conversion pipeline
        with path.open("rb") as fh:
            content_type = (
                "image/heic"
                if path.suffix.lower() in {".heic", ".heif"}
                else "application/octet-stream"
            )
            uploaded = SimpleUploadedFile(
                name=path.name,
                content=fh.read(),
                content_type=content_type,
            )

        try:
            processed = resize_image_file(uploaded)
        except Exception as exc:  # pragma: no cover
            raise CommandError(f"resize_image_file failed: {exc}")

        name = getattr(processed, "name", "<no name>")
        ctype = getattr(processed, "content_type", "<no content_type>")
        size_kb = round((getattr(processed, "size", 0) or 0) / 1024, 1)
        self.stdout.write(f"Processed file: name={name}, content_type={ctype}, size={size_kb} KB")
