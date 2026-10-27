# File: backend/app/infrastructure/storage/image_sanitizer.py
from dataclasses import dataclass
from io import BytesIO
from PIL import Image, ImageOps
from app.domain.exceptions.evidence_errors import EvidenceFileError


@dataclass(frozen=True)
class NormalizedProof:
    content: bytes
    width: int
    height: int


class _BoundedOutput(BytesIO):
    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit

    def write(self, data: bytes) -> int:
        if self.tell() + len(data) > self.limit:
            raise EvidenceFileError("TOO_LARGE")
        return super().write(data)


class ProofImageSanitizer:
    """Decode allowed raster formats and re-encode pixels without metadata."""

    def __init__(self, max_bytes: int, max_pixels: int, max_output_bytes: int):
        if not all(value > 0 for value in (max_bytes, max_pixels, max_output_bytes)):
            raise ValueError("Proof limits must be positive.")
        self.max_bytes = max_bytes
        self.max_pixels = max_pixels
        self.max_output_bytes = max_output_bytes

    def normalize(self, content: bytes) -> NormalizedProof:
        if not content:
            raise EvidenceFileError("INVALID_IMAGE")
        if len(content) > self.max_bytes:
            raise EvidenceFileError("TOO_LARGE")
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            image_format = "PNG"
        elif content.startswith(b"\xff\xd8\xff"):
            image_format = "JPEG"
        elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            image_format = "WEBP"
        else:
            raise EvidenceFileError("UNSUPPORTED_IMAGE")
        try:
            with Image.open(BytesIO(content), formats=[image_format]) as image:
                self._validate(image)
                image.verify()
            with Image.open(BytesIO(content), formats=[image_format]) as image:
                self._validate(image)
                image.load()
                with ImageOps.exif_transpose(image) as oriented:
                    mode = "RGBA" if "A" in oriented.getbands() or "transparency" in oriented.info else "RGB"
                    with oriented.convert(mode) as pixels, Image.new(mode, oriented.size) as clean:
                        clean.paste(pixels)
                        with _BoundedOutput(self.max_output_bytes) as output:
                            clean.save(output, format="PNG")
                            return NormalizedProof(output.getvalue(), clean.width, clean.height)
        except EvidenceFileError:
            raise
        except Image.DecompressionBombError:
            raise EvidenceFileError("TOO_LARGE") from None
        except Exception:
            raise EvidenceFileError("INVALID_IMAGE") from None

    def _validate(self, image: Image.Image) -> None:
        if image.width < 1 or image.height < 1:
            raise EvidenceFileError("INVALID_IMAGE")
        if image.width * image.height > self.max_pixels:
            raise EvidenceFileError("TOO_LARGE")
        if getattr(image, "n_frames", 1) != 1 or getattr(image, "is_animated", False):
            raise EvidenceFileError("UNSUPPORTED_IMAGE")
