from functools import lru_cache
import hashlib
from pathlib import Path
import re
from urllib.parse import quote, unquote

from django.conf import settings
from django.templatetags.static import static


_SUPPORTED_IMAGE_SUFFIXES = {".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
_MEMOJI_SECTIONS = ("male_memoji", "female_memoji")
DEFAULT_AVATAR_BACKGROUND = "lavender"
_AVATAR_BACKGROUND_OPTIONS = (
    ("lavender", "Lavender", "#D4C6F5"),
    ("mint", "Mint", "#A8F0D4"),
    ("sky", "Sky", "#C0CFF5"),
    ("peach", "Peach", "#F7D9A0"),
    ("rose", "Rose", "#F5C9DD"),
)
_AVATAR_BACKGROUND_KEYS = {option[0] for option in _AVATAR_BACKGROUND_OPTIONS}
_AVATAR_BACKGROUND_COLORS = {
    option[0]: option[2] for option in _AVATAR_BACKGROUND_OPTIONS
}
_AVATAR_FILENAME_PATTERN = re.compile(
    r"^(?:Person|Character)=(?P<person>[^,]+),\s*"
    r"Skin\s*[Tt]one=(?P<skin_tone>[^,]+),\s*"
    r"Posture=(?P<posture>\d+)\s+(?P<mood>.+)$"
)
_MOOD_LABEL_FIXUPS = {
    "luaghing": "Laughing",
}


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


@lru_cache(maxsize=1)
def _memoji_path_catalog():
    filenames = _memoji_filename_catalog()
    return {
        section: [f"{section}/{name}" for name in filenames.get(section, [])]
        for section in _MEMOJI_SECTIONS
    }


@lru_cache(maxsize=1)
def _memoji_path_set():
    catalog = _memoji_path_catalog()
    valid = set()
    for section in _MEMOJI_SECTIONS:
        valid.update(catalog.get(section, []))
    return valid


def _to_title_case(value):
    parts = (value or "").strip().split()
    return " ".join(part[:1].upper() + part[1:].lower() if part else "" for part in parts)


def _friendly_mood_label(mood_raw):
    normalized_mood = (mood_raw or "").strip()
    if not normalized_mood:
        return ""

    fixed = _MOOD_LABEL_FIXUPS.get(normalized_mood.lower())
    if fixed:
        return fixed

    return _to_title_case(normalized_mood)


def parse_avatar_filename_metadata(filename):
    stem = Path(filename or "").stem.strip()
    match = _AVATAR_FILENAME_PATTERN.match(stem)
    if not match:
        return {
            "person": "",
            "skin_tone": "",
            "posture": 0,
            "mood_raw": "",
            "mood_label": "",
        }

    person = match.group("person").strip()
    skin_tone = _to_title_case(match.group("skin_tone"))
    posture = int(match.group("posture"))
    mood_raw = match.group("mood").strip()

    return {
        "person": person,
        "skin_tone": skin_tone,
        "posture": posture,
        "mood_raw": mood_raw,
        "mood_label": _friendly_mood_label(mood_raw),
    }


def _stable_digest(seed):
    normalized_seed = (seed or "").strip() or "anonymous-user"
    return hashlib.sha256(normalized_seed.encode("utf-8")).hexdigest()


def normalize_avatar_background(background_key):
    key = (background_key or "").strip().lower()
    if key in _AVATAR_BACKGROUND_KEYS:
        return key
    return DEFAULT_AVATAR_BACKGROUND


def get_avatar_background_color(background_key):
    key = normalize_avatar_background(background_key)
    return _AVATAR_BACKGROUND_COLORS.get(
        key, _AVATAR_BACKGROUND_COLORS[DEFAULT_AVATAR_BACKGROUND]
    )


def get_avatar_background_options():
    return [
        {"key": key, "label": label, "color": color}
        for key, label, color in _AVATAR_BACKGROUND_OPTIONS
    ]


def _select_memoji_path(seed):
    catalog = _memoji_path_catalog()
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
    return files[file_index]


def normalize_avatar_choice(avatar_choice):
    value = unquote((avatar_choice or "").strip()).replace("\\", "/")
    if value.startswith("/"):
        value = value[1:]
    if value.startswith("static/"):
        value = value[7:]
    return value


def is_valid_avatar_choice(avatar_choice):
    normalized = normalize_avatar_choice(avatar_choice)
    if not normalized:
        return False
    return normalized in _memoji_path_set()


def build_avatar_url_from_path(avatar_path):
    normalized = normalize_avatar_choice(avatar_path)
    if not is_valid_avatar_choice(normalized):
        return ""
    return quote(static(normalized), safe="/:%?&=#")


def build_user_avatar_path(user):
    selected_choice = normalize_avatar_choice(getattr(user, "avatar_choice", ""))
    if is_valid_avatar_choice(selected_choice):
        return selected_choice

    seed = f"{getattr(user, 'pk', '')}:{getattr(user, 'email', '')}"
    return _select_memoji_path(seed)


@lru_cache(maxsize=1)
def get_avatar_sections():
    catalog = _memoji_path_catalog()
    return {
        "male": [
            {
                "path": path,
                "url": build_avatar_url_from_path(path),
                **parse_avatar_filename_metadata(Path(path).name),
            }
            for path in catalog["male_memoji"]
        ],
        "female": [
            {
                "path": path,
                "url": build_avatar_url_from_path(path),
                **parse_avatar_filename_metadata(Path(path).name),
            }
            for path in catalog["female_memoji"]
        ],
    }


def build_user_avatar_url(user):
    avatar_static_path = build_user_avatar_path(user)
    if not avatar_static_path:
        return ""
    return build_avatar_url_from_path(avatar_static_path)
