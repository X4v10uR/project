"""Top-level URL routes for Subly."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.views import serve as serve_staticfiles
from django.shortcuts import render
from django.urls import include, path, re_path
from django.views.static import serve as serve_media

from dashboard import views as dashboard_views


def custom_404_view(request, exception):
    return render(
        request,
        "404.html",
        {
            "hide_global_notifications": True,
            "suppress_base_messages": True,
        },
        status=404,
    )


urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('subscriptions/', include('subscriptions.urls')),
    path('dashboard/balance-stats/', dashboard_views.balance_stats_page, name='balance_stats'),
    path('dashboard/', include('dashboard.urls')),
    path('', dashboard_views.landing_page, name='landing'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if not settings.DEBUG:
    urlpatterns += [
        re_path(r"^static/(?P<path>.*)$", serve_staticfiles, {"insecure": True}),
        re_path(r"^media/(?P<path>.*)$", serve_media, {"document_root": settings.MEDIA_ROOT}),
    ]

handler404 = "subly.urls.custom_404_view"
