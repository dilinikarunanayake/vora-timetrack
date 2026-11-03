"""
Top-level URL routing for Vora TimeTrack.

Django checks each incoming URL against this list, top to bottom.
Each app keeps its own urls.py, and we "include" it here.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]
