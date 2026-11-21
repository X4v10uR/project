import colorsys
import hashlib

from subscriptions.color_utils import normalize_subscription_display_color

from .constants import CARD_COLOR_PALETTE, SERVICE_COLOR_PREFERENCES


def _normalize_service_name(service_name):
    return (service_name or '').strip().lower()


def _stable_bucket(value):
    digest = hashlib.sha256(value.encode('utf-8')).hexdigest()
    return int(digest[:8], 16)


def _hex_to_rgb(color):
    if not color:
        return None

    token = color.strip().lower()
    if not token.startswith('#'):
        return None

    if len(token) == 4:
        token = '#' + ''.join(channel * 2 for channel in token[1:])
    elif len(token) == 9:
        token = token[:7]

    if len(token) != 7:
        return None

    try:
        return (
            int(token[1:3], 16),
            int(token[3:5], 16),
            int(token[5:7], 16),
        )
    except ValueError:
        return None


def _rgb_to_hex(red, green, blue):
    return (
        f'#{max(0, min(255, int(round(red)))):02X}'
        f'{max(0, min(255, int(round(green)))):02X}'
        f'{max(0, min(255, int(round(blue)))):02X}'
    )


def _ensure_distinct_color(candidate, seed_text, used_colors):
    if not candidate:
        return _pick_distinct_palette_color(seed_text, used_colors)

    if candidate not in used_colors:
        return candidate

    rgb = _hex_to_rgb(candidate)
    if not rgb:
        return _pick_distinct_palette_color(seed_text, used_colors)

    red, green, blue = [channel / 255.0 for channel in rgb]
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)

    for delta in (0.05, -0.05, 0.1, -0.1, 0.15, -0.15):
        nudged_lightness = min(max(lightness + delta, 0.2), 0.82)
        nudged_red, nudged_green, nudged_blue = colorsys.hls_to_rgb(
            hue, nudged_lightness, saturation
        )
        nudged_color = _rgb_to_hex(
            nudged_red * 255, nudged_green * 255, nudged_blue * 255
        )
        if nudged_color not in used_colors:
            return nudged_color

    return _pick_distinct_palette_color(seed_text, used_colors)


def _generate_pastel_color(seed_text, used_colors):
    base_hue = _stable_bucket(seed_text) % 360
    for offset in range(0, 360, 17):
        candidate = f"hsl({(base_hue + offset) % 360} 65% 74%)"
        if candidate not in used_colors:
            return candidate
    return f"hsl({base_hue} 65% 74%)"


def _pick_distinct_palette_color(seed_text, used_colors):
    if not CARD_COLOR_PALETTE:
        return _generate_pastel_color(seed_text, used_colors)

    start_index = _stable_bucket(seed_text) % len(CARD_COLOR_PALETTE)
    for step in range(len(CARD_COLOR_PALETTE)):
        candidate = CARD_COLOR_PALETTE[(start_index + step) % len(CARD_COLOR_PALETTE)]
        if candidate not in used_colors:
            return candidate
    return _generate_pastel_color(seed_text, used_colors)


def build_service_color_map(subscriptions, recent_transactions):
    service_colors = {}

    def _add_service(name, color=""):
        normalized = _normalize_service_name(name)
        if normalized and not service_colors.get(normalized):
            service_colors[normalized] = normalize_subscription_display_color(color)

    for subscription in subscriptions:
        _add_service(subscription.service_name, getattr(subscription, "display_color", ""))
    for transaction in recent_transactions:
        _add_service(transaction.service_name_snapshot)

    used_colors = {color for color in service_colors.values() if color}
    color_map = {}

    for normalized, custom_color in service_colors.items():
        if custom_color:
            color_map[normalized] = custom_color
            continue

        preferred = SERVICE_COLOR_PREFERENCES.get(normalized)
        if preferred:
            color = _ensure_distinct_color(preferred, normalized, used_colors)
        else:
            color = _pick_distinct_palette_color(normalized, used_colors)

        color_map[normalized] = color
        used_colors.add(color)

    return color_map


def service_background_style(service_name, service_color_map):
    normalized = _normalize_service_name(service_name)
    color = service_color_map.get(normalized)
    if not color:
        color = _pick_distinct_palette_color(normalized or 'service', set())
    return f'background-color: {color};'
