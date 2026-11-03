"""
Top-level URL routing for Vora TimeTrack.

Django checks each incoming URL against this list, top to bottom.
Each app keeps its own urls.py, and we "include" it here.
"""

from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Vora TimeTrack administration"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("reports/", include("reports.urls")),
    path("", include("timetrack.urls")),
    path("", include("core.urls")),
]
