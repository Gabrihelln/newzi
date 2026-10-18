"""Profile photos uploaded from the app (Editar perfil › Trocar foto).

The app sends the picked image as base64; it is decoded, checked to be a real image, turned upright, shrunk
to at most AVATAR_SIZE pixels and re-encoded as JPEG (which also drops EXIF data such as the location).
Files get a random name, so their public URL cannot be guessed, and a new photo or a deleted account
removes the previous file.
"""
import base64
import binascii
import io
import os
import re
import uuid
from pathlib import Path

from .paths import BACKEND_DATA
from .timeutil import now_iso

AVATAR_SIZE = 512
MAX_UPLOAD_BYTES = 700 * 1024
URL_PREFIX = "/api/v1/avatars/"
_NAME = re.compile(r"^[0-9a-f]{32}\.jpg$")


def avatar_root():
    """AVATAR_STORAGE_ROOT, else next to the audio storage (writable on the server), else backend/data."""
    explicit = os.getenv("AVATAR_STORAGE_ROOT")
    if explicit:
        return Path(explicit)
    audio = os.getenv("AUDIO_STORAGE_ROOT")
    return Path(audio).parent / "avatars" if audio else BACKEND_DATA / "avatars"


def avatar_path(name):
    """The stored file for a public avatar name, or None for anything that is not one of ours."""
    if not _NAME.match(name or ""):
        return None
    path = avatar_root() / name
    return path if path.is_file() else None


def photo_url(user):
    return URL_PREFIX + user["avatar_file"] if user and user.get("avatar_file") else None


def _remove(name):
    path = avatar_path(name)
    if path:
        path.unlink(missing_ok=True)


def save_avatar(repo, uid, image_base64):
    """Store a new photo for ``uid`` and return its public URL path. Raises ValueError for a bad image."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        raw = base64.b64decode(str(image_base64 or ""), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("image_base64 must be base64") from None
    if not raw:
        raise ValueError("image_base64 is required")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("image is too large")
    try:
        with Image.open(io.BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("file is not an image") from None
    image.thumbnail((AVATAR_SIZE, AVATAR_SIZE))
    root = avatar_root()
    root.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex + ".jpg"
    image.save(root / name, "JPEG", quality=85, optimize=True)
    previous = repo.db.execute("SELECT avatar_file FROM users WHERE id=?", (uid,)).fetchone()
    repo.db.execute("UPDATE users SET avatar_file=?,updated_at=? WHERE id=?", (name, now_iso(), uid))
    repo.db.commit()
    if previous and previous["avatar_file"]:
        _remove(previous["avatar_file"])
    return URL_PREFIX + name


def delete_avatar_file(user):
    if user and user.get("avatar_file"):
        _remove(user["avatar_file"])
