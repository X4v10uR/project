import re


LIGHT_SUBSCRIPTION_COLOR_PRESETS = [
    "#F9F871",
    "#7BCFC0",
    "#B5A5E7",
    "#AFC0DE",
    "#F4C3A8",
    "#9ED6EA",
    "#C3DDA6",
    "#E7B3C6",
    "#D8C6A5",
    "#C7BEEA",
]

HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-F]{6}$")


def normalize_subscription_display_color(raw_value):
    raw = str(raw_value or "").strip().upper()
    if not raw:
        return ""

    if not raw.startswith("#"):
        raw = f"#{raw}"

    if len(raw) == 4 and re.fullmatch(r"#[0-9A-F]{3}", raw):
        raw = "#" + "".join(ch * 2 for ch in raw[1:])

    if not HEX_COLOR_PATTERN.fullmatch(raw):
        return ""

    return raw
