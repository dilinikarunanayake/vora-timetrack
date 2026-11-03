"""Public pages that don't need a login."""

from django.shortcuts import render


def home(request):
    """Landing page."""
    return render(request, "core/home.html")
