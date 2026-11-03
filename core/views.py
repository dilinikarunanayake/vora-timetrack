"""Public pages that don't need a login."""

from django.db import connection
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache


def home(request):
    """Landing page."""
    return render(request, "core/home.html")


@never_cache
def healthz(request):
    """
    Health check for the hosting company: "is the app up and can it reach the
    database?" Returns 200 "ok", or 503 if the database can't be reached.
    It reveals nothing else, so it's safe to leave public.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return HttpResponse("database unavailable", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")
