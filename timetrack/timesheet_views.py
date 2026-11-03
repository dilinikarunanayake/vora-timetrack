"""
Views for weekly timesheets: viewing a week, submitting it, and the
manager approval workflow.

The status rules themselves live on the Timesheet model (submit, approve,
reject, ...). These views only find the right timesheet for the signed-in
user, call the model method, and report the result.
"""

from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import ListView, TemplateView

from .access import CanLogTimeMixin, ManagerRequiredMixin, timesheets_to_review, visible_timesheets
from .models import TimeEntry, Timesheet, week_start


def week_context(user, engineer, monday, timesheet):
    """Everything the week page needs, for either the owner or a reviewer."""
    entries = (
        TimeEntry.objects.filter(engineer=engineer, work_date__gte=monday, work_date__lte=monday + timedelta(days=6))
        .select_related("task__project")
        .order_by("work_date", "created_at")
    )
    days = []
    for offset in range(7):
        day = monday + timedelta(days=offset)
        day_entries = [e for e in entries if e.work_date == day]
        days.append({"date": day, "entries": day_entries, "total": sum(e.hours for e in day_entries)})

    total = sum(e.hours for e in entries)
    billable = sum(e.hours for e in entries if e.is_billable)
    is_owner = user.pk == engineer.pk
    status = timesheet.status if timesheet else Timesheet.Status.DRAFT
    editable = status in Timesheet.EDITABLE

    return {
        "engineer": engineer,
        "timesheet": timesheet,
        "status": status,
        "status_label": Timesheet.Status(status).label,
        "week_start": monday,
        "week_end": monday + timedelta(days=6),
        "days": days,
        "totals": {"total": total, "billable": billable, "non_billable": total - billable},
        "actions": timesheet.actions.select_related("by") if timesheet else [],
        "is_owner": is_owner,
        "editable": editable,
        # Which buttons to show. The model re-checks every rule when clicked.
        "can_add": is_owner and editable and monday <= timezone.localdate(),
        "can_submit": is_owner and editable and bool(total) and monday <= timezone.localdate(),
        "can_withdraw": is_owner and status == Timesheet.Status.SUBMITTED,
        "can_review": bool(timesheet) and status == Timesheet.Status.SUBMITTED and timesheet.can_review(user),
        "can_reopen": bool(timesheet) and status == Timesheet.Status.APPROVED and user.is_director and not is_owner,
    }


class MyTimesheetsView(CanLogTimeMixin, ListView):
    """The signed-in user's own timesheets, newest week first."""

    template_name = "timetrack/my_timesheets.html"
    context_object_name = "timesheets"
    paginate_by = 20

    def get_queryset(self):
        return (
            Timesheet.objects.filter(engineer=self.request.user)
            .annotate(total=Sum("entries__hours"), billable=Sum("entries__hours", filter=Q(entries__is_billable=True)))
            # hide empty drafts (e.g. a week whose only entry was moved elsewhere)
            .exclude(Q(status=Timesheet.Status.DRAFT) & Q(total__isnull=True))
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["this_week"] = week_start(timezone.localdate())
        return ctx


class MyWeekView(CanLogTimeMixin, TemplateView):
    """/timesheets/week/2026-11-02/ : one of the user's own weeks, even if it has no entries yet."""

    template_name = "timetrack/timesheet_detail.html"

    def get(self, request, week):
        try:
            day = date.fromisoformat(week)
        except ValueError:
            raise Http404("Not a valid date")
        monday = week_start(day)
        if monday != day:  # always show weeks by their Monday
            return redirect("timetrack:my_week", week=monday.isoformat())
        if monday > week_start(timezone.localdate()):
            messages.info(request, "That week hasn't started yet.")
            return redirect("timetrack:my_week", week=week_start(timezone.localdate()).isoformat())
        return super().get(request, week=week)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        monday = date.fromisoformat(kwargs["week"])
        timesheet = Timesheet.objects.filter(engineer=user, week_start=monday).first()
        ctx.update(week_context(user, user, monday, timesheet))
        ctx["prev_week"] = monday - timedelta(days=7)
        if monday < week_start(timezone.localdate()):
            ctx["next_week"] = monday + timedelta(days=7)
        return ctx


class TimesheetDetailView(LoginRequiredMixin, TemplateView):
    """/timesheets/15/ : any timesheet within the user's scope (used by reviewers)."""

    template_name = "timetrack/timesheet_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        timesheet = get_object_or_404(visible_timesheets(user), pk=kwargs["pk"])
        if timesheet.engineer_id == user.pk:
            ctx["own_week_url"] = reverse("timetrack:my_week", args=[timesheet.week_start.isoformat()])
        ctx.update(week_context(user, timesheet.engineer, timesheet.week_start, timesheet))
        return ctx


class ApprovalsView(ManagerRequiredMixin, ListView):
    """Managers' and directors' queue of submitted timesheets."""

    template_name = "timetrack/approvals.html"
    context_object_name = "waiting"

    def get_queryset(self):
        return (
            timesheets_to_review(self.request.user)
            .annotate(total=Sum("entries__hours"), billable=Sum("entries__hours", filter=Q(entries__is_billable=True)))
            .order_by("week_start", "engineer__first_name")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["recent"] = (
            visible_timesheets(self.request.user)
            .filter(status__in=[Timesheet.Status.APPROVED, Timesheet.Status.REJECTED])
            .exclude(engineer=self.request.user)
            .annotate(total=Sum("entries__hours"))
            .order_by("-reviewed_at")[:15]
        )
        return ctx


class TimesheetActionView(LoginRequiredMixin, View):
    """POST /timesheets/<pk>/<action>/ : submit, withdraw, approve, reject or reopen."""

    http_method_names = ["post"]  # changing data must never happen on a plain link (GET)

    def post(self, request, pk, action):
        user = request.user
        comment = request.POST.get("comment", "").strip()

        if action == "submit":
            # Only the owner can submit, so look only among their own timesheets.
            timesheet = get_object_or_404(Timesheet, pk=pk, engineer=user)
        else:
            timesheet = get_object_or_404(visible_timesheets(user), pk=pk)

        handlers = {
            "submit": (lambda: timesheet.submit(user), "Timesheet submitted for approval. The week is now locked."),
            "withdraw": (lambda: timesheet.withdraw(user), "Timesheet withdrawn. You can edit the week again."),
            "approve": (lambda: timesheet.approve(user, comment), f"Approved {timesheet}."),
            "reject": (lambda: timesheet.reject(user, comment), f"Rejected {timesheet}. The engineer can now correct it."),
            "reopen": (lambda: timesheet.reopen(user, comment), f"Reopened {timesheet} for corrections."),
        }
        if action not in handlers:
            raise Http404
        run, success_message = handlers[action]

        try:
            run()  # PermissionDenied propagates and Django shows 403 Forbidden
            messages.success(request, success_message)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))

        next_url = request.POST.get("next")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        if timesheet.engineer_id == user.pk:
            return redirect("timetrack:my_week", week=timesheet.week_start.isoformat())
        return redirect("timetrack:timesheet_detail", pk=timesheet.pk)
