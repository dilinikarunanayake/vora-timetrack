"""URL routes for the core app (landing page and dashboard)."""

from django.urls import path

from . import views

app_name = "core"  # lets templates use {% url 'core:dashboard' %}

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
]
