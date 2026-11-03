"""URL routes for time tracking. <int:pk> captures a record ID from the address."""

from django.urls import path

from . import rate_views, timesheet_views, views

app_name = "timetrack"

urlpatterns = [
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    # Time entries
    path("entries/", views.EntryListView.as_view(), name="entry_list"),
    path("entries/add/", views.EntryCreateView.as_view(), name="entry_add"),
    path("entries/<int:pk>/edit/", views.EntryUpdateView.as_view(), name="entry_edit"),
    path("entries/<int:pk>/delete/", views.EntryDeleteView.as_view(), name="entry_delete"),
    # Weekly timesheets
    path("timesheets/", timesheet_views.MyTimesheetsView.as_view(), name="my_timesheets"),
    path("timesheets/week/<str:week>/", timesheet_views.MyWeekView.as_view(), name="my_week"),
    path("timesheets/approvals/", timesheet_views.ApprovalsView.as_view(), name="approvals"),
    path("timesheets/<int:pk>/", timesheet_views.TimesheetDetailView.as_view(), name="timesheet_detail"),
    path(
        "timesheets/<int:pk>/<str:action>/",
        timesheet_views.TimesheetActionView.as_view(),
        name="timesheet_action",
    ),
    # Billing rates (directors only)
    path("rates/", rate_views.RateListView.as_view(), name="rate_list"),
    path("rates/add/", rate_views.RateCreateView.as_view(), name="rate_add"),
    path("rates/<int:pk>/edit/", rate_views.RateUpdateView.as_view(), name="rate_edit"),
    path("rates/<int:pk>/delete/", rate_views.RateDeleteView.as_view(), name="rate_delete"),
    path("rates/price-missing/", rate_views.PriceMissingView.as_view(), name="rate_price_missing"),
    # Projects and tasks
    path("projects/", views.ProjectListView.as_view(), name="project_list"),
    path("projects/add/", views.ProjectCreateView.as_view(), name="project_add"),
    path("projects/<int:pk>/", views.ProjectDetailView.as_view(), name="project_detail"),
    path("projects/<int:pk>/edit/", views.ProjectUpdateView.as_view(), name="project_edit"),
    path("projects/<int:project_pk>/tasks/add/", views.TaskCreateView.as_view(), name="task_add"),
    path("projects/<int:project_pk>/tasks/<int:pk>/edit/", views.TaskUpdateView.as_view(), name="task_edit"),
]
