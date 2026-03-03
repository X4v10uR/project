from django.conf import settings


def runtime_flags(request):
    has_channels = bool(getattr(settings, "HAS_CHANNELS", False))
    has_channel_layer = bool(getattr(settings, "CHANNEL_LAYERS", None))
    return {
        "notifications_ws_enabled": has_channels and has_channel_layer,
    }

