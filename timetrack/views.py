"""
Views for time entries, projects and tasks.

These are CLASS-BASED VIEWS: Django's generic ListView, CreateView,
UpdateView, etc. do the repetitive work (fetch, validate, save, redirect).
We only override the parts that differ, mostly *which records the user
is allowed to see* (get_queryset) and *who may open the page* (mixins).
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Concat
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from .access import (
    CanLogTimeMixin,
    ManagerRequiredMixin,
    can_log_time,
    timesheets_to_review,
    visible_entries,
    visible_projects,
)
from .billing import can_see_costs, unpriced_approved_entries
from .forms import EntryFilterForm, ProjectForm, TaskForm, TimeEntryForm
from .models import Project, Task, TimeEntry, Timesheet, week_start

ZERO = Decimal("0")


def hours_summary(entries):
    """Total, billable and non-billable hours for a queryset of entries."""
    totals = entries.aggregate(
        total=Sum("hours"),
        billable=Sum("hours", filter=Q(is_billable=True)),
    )
    total = totals["total"] or ZERO
    billable = totals["billable"] or ZERO
    return {
        "total": total,
        "billable": billable,
        "non_billable": total - billable,
        "billable_percent": round(billable / total * 100) if total else 0,
    }


# --- Dashboard ------------------------------------------------------------

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "timetrack/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        monday = week_start(timezone.localdate())
        entries = visible_entries(user).filter(work_date__gte=monday, work_date__lte=monday + timedelta(days=6))

        ctx["week_start"] = monday
        ctx["week_end"] = monday + timedelta(days=6)
        ctx["summary"] = hours_summary(entries)
        ctx["recent_entries"] = visible_entries(user).select_related("timesheet")[:8]
        ctx["can_log_time"] = can_log_time(user)
        if user.can_manage_projects:
            ctx["approvals_count"] = timesheets_to_review(user).count()
        if ctx["can_log_time"]:
            sheet = Timesheet.objects.filter(engineer=user, week_start=monday).first()
            ctx["my_week_status"] = sheet.get_status_display() if sheet else "Not started"
            # Last week still not submitted? Remind them.
            last = Timesheet.objects.filter(
                engineer=user, week_start=monday - timedelta(days=7), status__in=Timesheet.EDITABLE
            ).first()
            ctx["last_week_open"] = last if last and last.entries.exists() else None

        # The breakdown table changes with the role.
        if user.is_director:
            ctx["breakdown_title"] = "Hours by business"
            label = F("task__project__business__name")
        elif user.is_manager:
            ctx["breakdown_title"] = "Hours by engineer"
            label = Concat("engineer__first_name", Value(" "), "engineer__last_name")
        else:
            ctx["breakdown_title"] = "Hours by project"
            label = F("task__project__name")

        ctx["breakdown"] = (
            entries.values(label=label)
            .annotate(total=Sum("hours"), billable=Sum("hours", filter=Q(is_billable=True)))
            .order_by("-total")
        )
        return ctx


# --- Time entries ---------------------------------------------------------

class EntryListView(LoginRequiredMixin, ListView):
    template_name = "timetrack/entry_list.html"
    context_object_name = "entries"
    paginate_by = 25

    def get_queryset(self):
        qs = visible_entries(self.request.user).select_related("timesheet")
        self.filter_form = EntryFilterForm(self.request.GET or None, user=self.request.user)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data["start"]:
                qs = qs.filter(work_date__gte=data["start"])
            if data["end"]:
                qs = qs.filter(work_date__lte=data["end"])
            if data["project"]:
                qs = qs.filter(task__project=data["project"])
        self.summary = hours_summary(qs)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_form"] = self.filter_form
        ctx["summary"] = self.summary
        ctx["can_log_time"] = can_log_time(self.request.user)
        query = self.request.GET.copy()
        query.pop("page", None)
        ctx["querystring"] = query.urlencode()  # keeps filters when changing page
        return ctx


def safe_next(request, fallback):
    """Return ?next=... only if it points back into this site (prevents open redirects)."""
    url = request.POST.get("next") or request.GET.get("next")
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}):
        return url
    return fallback


class ReturnUrlMixin:
    """Gives entry forms a safe 'next' (where to go after saving) and Cancel link."""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["next_url"] = safe_next(self.request, "")
        ctx["cancel_url"] = safe_next(self.request, reverse("timetrack:entry_list"))
        return ctx


class OwnEntryMixin(ReturnUrlMixin, CanLogTimeMixin):
    """Edit/delete: only the engineer's OWN entries can be found at all,
    and entries in a submitted or approved week can't be changed."""

    def get_queryset(self):
        return TimeEntry.objects.filter(engineer=self.request.user).select_related("task__project", "timesheet")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            entry = self.get_queryset().filter(pk=kwargs["pk"]).first()
            if entry and entry.is_locked:
                messages.error(
                    request,
                    f"The week of {entry.timesheet.week_start:%d %b %Y} is "
                    f"{entry.timesheet.get_status_display().lower()} and locked.",
                )
                return redirect(safe_next(request, reverse("timetrack:entry_list")))
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return safe_next(self.request, reverse("timetrack:entry_list"))


class EntryCreateView(ReturnUrlMixin, CanLogTimeMixin, CreateView):
    form_class = TimeEntryForm
    template_name = "timetrack/entry_form.html"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def get_initial(self):
        # The week page links here with ?date=YYYY-MM-DD to pre-fill the day.
        initial = super().get_initial()
        try:
            initial["work_date"] = date.fromisoformat(self.request.GET.get("date", ""))
        except ValueError:
            pass
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Time entry saved.")
        return super().form_valid(form)

    def get_success_url(self):
        if "save_add" in self.request.POST:
            url = reverse("timetrack:entry_add")
            next_url = safe_next(self.request, "")
            return f"{url}?next={next_url}" if next_url else url
        return safe_next(self.request, reverse("timetrack:entry_list"))


class EntryUpdateView(OwnEntryMixin, UpdateView):
    form_class = TimeEntryForm
    template_name = "timetrack/entry_form.html"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def form_valid(self, form):
        messages.success(self.request, "Time entry updated.")
        return super().form_valid(form)


class EntryDeleteView(OwnEntryMixin, DeleteView):
    template_name = "timetrack/entry_confirm_delete.html"

    def form_valid(self, form):
        messages.success(self.request, "Time entry deleted.")
        return super().form_valid(form)


# --- Projects and tasks ---------------------------------------------------

class ProjectListView(LoginRequiredMixin, ListView):
    template_name = "timetrack/project_list.html"
    context_object_name = "projects"

    def get_queryset(self):
        return visible_projects(self.request.user).annotate(
            task_count=Count("tasks", distinct=True),
            total_hours=Sum("tasks__time_entries__hours"),
        )


class ProjectDetailView(LoginRequiredMixin, DetailView):
    template_name = "timetrack/project_detail.html"
    context_object_name = "project"

    def get_queryset(self):
        return visible_projects(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tasks"] = self.object.tasks.annotate(total_hours=Sum("time_entries__hours"))
        entries = TimeEntry.objects.filter(task__project=self.object)
        ctx["summary"] = hours_summary(entries)
        ctx["report_query"] = urlencode({
            "project": self.object.pk, "group_by": "task", "status": "all",
            "start": (self.object.start_date or date(timezone.localdate().year, 1, 1)).isoformat(),
            "end": timezone.localdate().isoformat(),
        })
        if can_see_costs(self.request.user):
            unpriced = unpriced_approved_entries(entries)
            ctx["value"] = {
                # Sum of hours x rate, calculated by the database in one query.
                "approved": entries.filter(rate__isnull=False).aggregate(
                    v=Sum(F("hours") * F("rate"), output_field=DecimalField(max_digits=14, decimal_places=2))
                )["v"] or ZERO,
                "approved_hours": entries.filter(timesheet__status="APPROVED", is_billable=True).aggregate(h=Sum("hours"))["h"] or ZERO,
                "unpriced_hours": unpriced.aggregate(h=Sum("hours"))["h"] or ZERO,
            }
        return ctx


class ProjectCreateView(ManagerRequiredMixin, CreateView):
    form_class = ProjectForm
    template_name = "timetrack/project_form.html"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def get_success_url(self):
        messages.success(self.request, "Project saved.")
        return reverse("timetrack:project_detail", args=[self.object.pk])


class ProjectUpdateView(ProjectCreateView, UpdateView):
    def get_queryset(self):
        return visible_projects(self.request.user)


class ProjectScopedMixin(ManagerRequiredMixin):
    """Loads the project from the URL, but only if it's within the user's scope."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.project = get_object_or_404(visible_projects(request.user), pk=kwargs["project_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "project": self.project}

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "project": self.project}

    def get_success_url(self):
        messages.success(self.request, "Task saved.")
        return reverse("timetrack:project_detail", args=[self.project.pk])


class TaskCreateView(ProjectScopedMixin, CreateView):
    form_class = TaskForm
    template_name = "timetrack/task_form.html"


class TaskUpdateView(ProjectScopedMixin, UpdateView):
    form_class = TaskForm
    template_name = "timetrack/task_form.html"

    def get_queryset(self):
        return Task.objects.filter(project=self.project)
