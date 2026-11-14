"""Trainee photo storage (resized, re-encoded, unguessable file names)."""
from __future__ import annotations

import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from ..core.config import settings
from ..core.errors import ServiceError

MAX_UPLOAD_BYTES = 6 * 1024 * 1024
PHOTO_SIZE = 480


def media_root() -> Path:
    root = Path(settings.media_dir)
    (root / "photos").mkdir(parents=True, exist_ok=True)
    return root


def save_photo(data: bytes) -> str:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ServiceError("حجم الصورة كبير (الحد الأقصى 6 ميجا)", code="photo_too_large")
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError):
        raise ServiceError("الملف ليس صورة صالحة", code="invalid_image") from None
    image = ImageOps.exif_transpose(image).convert("RGB")
    image = ImageOps.fit(image, (PHOTO_SIZE, PHOTO_SIZE), method=Image.Resampling.LANCZOS)  # square crop
    name = f"photos/{uuid.uuid4().hex}.jpg"
    image.save(media_root() / name, "JPEG", quality=85, optimize=True)
    return name


def delete_photo(relative: str | None) -> None:
    if not relative:
        return
    path = (media_root() / relative).resolve()
    try:
        path.relative_to(media_root().resolve())
    except ValueError:
        return
    path.unlink(missing_ok=True)
