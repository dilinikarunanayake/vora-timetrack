"""URL routes for reports and CSV downloads."""

from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportView.as_view(), name="report"),
    path("export/summary.csv", views.CsvExportView.as_view(kind="summary"), name="export_summary"),
    path("export/detail.csv", views.CsvExportView.as_view(kind="detail"), name="export_detail"),
]
