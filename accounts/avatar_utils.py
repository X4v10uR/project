from functools import lru_cache
import hashlib
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.templatetags.static import static


_SUPPORTED_IMAGE_SUFFIXES = {".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp"}


@lru_cache(maxsize=1)
def _memoji_filename_catalog():
    base_dir = Path(settings.BASE_DIR) / "avatars"
    male_dir = base_dir / "male_memoji"
    female_dir = base_dir / "female_memoji"

    male_files = sorted(
        path.name
        for path in male_dir.glob("*")
        if path.is_file() and path.suffix.lower() in _SUPPORTED_IMAGE_SUFFIXES
    )
    female_files = sorted(
        path.name
        for path in female_dir.glob("*")
        if path.is_file() and path.suffix.lower() in _SUPPORTED_IMAGE_SUFFIXES
    )
    return {"male_memoji": male_files, "female_memoji": female_files}


def _stable_digest(seed):
    normalized_seed = (seed or "").strip() or "anonymous-user"
    return hashlib.sha256(normalized_seed.encode("utf-8")).hexdigest()


def _select_memoji_path(seed):
    catalog = _memoji_filename_catalog()
    male_files = catalog["male_memoji"]
    female_files = catalog["female_memoji"]
    digest = _stable_digest(seed)
    bucket = int(digest[:16], 16)

    if male_files and female_files:
        folder = "male_memoji" if bucket % 2 == 0 else "female_memoji"
    elif male_files:
        folder = "male_memoji"
    elif female_files:
        folder = "female_memoji"
    else:
        return ""

    files = catalog[folder]
    file_index = int(digest[16:32], 16) % len(files)
    return f"{folder}/{files[file_index]}"


def build_user_avatar_url(user):
    profile_photo = getattr(user, "profile_photo", None)
    if profile_photo:
        try:
            return profile_photo.url
        except ValueError:
            pass

    seed = f"{getattr(user, 'pk', '')}:{getattr(user, 'email', '')}"
    avatar_static_path = _select_memoji_path(seed)
    if not avatar_static_path:
        return ""
    return quote(static(avatar_static_path), safe="/:%?&=#")
