"""
Views for the core app.

A view is a Python function that receives a web request and returns a
response, usually by rendering an HTML template with some data ("context").
"""

from django.shortcuts import render

from .sample_data import dashboard_summary


def home(request):
    """Public landing page."""
    return render(request, "core/home.html", {"summary": dashboard_summary()})


def dashboard(request):
    """Dashboard showing SAMPLE time-tracking figures (no login yet - Phase 2)."""
    context = dashboard_summary()
    context["week_label"] = "Week commencing 2 Nov 2026 (sample data)"
    return render(request, "core/dashboard.html", context)
