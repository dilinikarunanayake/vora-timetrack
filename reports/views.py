"""
Report page and CSV downloads.

All three views read the same filters from the address bar (?start=...&end=...),
so a report can be bookmarked or shared and the CSV matches the screen.
"""

import csv
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from .engine import build_report
from .forms import ReportForm


def quick_ranges(today):
    """Shortcut date ranges shown above the report."""
    this_monday = today - timedelta(days=today.weekday())
    first_this_month = today.replace(day=1)
    last_month_end = first_this_month - timedelta(days=1)
    return [
        ("This week", this_monday, today),
        ("Last week", this_monday - timedelta(days=7), this_monday - timedelta(days=1)),
        ("This month", first_this_month, today),
        ("Last month", last_month_end.replace(day=1), last_month_end),
        ("Year to date", today.replace(month=1, day=1), today),
    ]


class ReportMixin(LoginRequiredMixin):
    def get_form(self):
        return ReportForm(self.request.GET, user=self.request.user)


class ReportView(ReportMixin, TemplateView):
    template_name = "reports/report.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        form = self.get_form()
        ctx["form"] = form
        if form.is_valid():
            ctx["report"] = build_report(self.request.user, form.cleaned_data)
            ctx["querystring"] = self.request.GET.urlencode()
            params = self.request.GET.copy()
            ranges = []
            for label, start, end in quick_ranges(timezone.localdate()):
                params["start"], params["end"] = start.isoformat(), end.isoformat()
                active = start == form.cleaned_data["start"] and end == form.cleaned_data["end"]
                ranges.append({"label": label, "query": params.urlencode(), "active": active})
            ctx["quick_ranges"] = ranges
        return ctx


# --- CSV ----------------------------------------------------------------------

def csv_safe(value):
    """
    Stop "CSV injection": spreadsheet apps treat a cell starting with = + - @
    as a formula. A description like '=HYPERLINK(...)' could run when opened
    in Excel, so we prefix such text with an apostrophe.
    """
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


class CsvExportView(ReportMixin, View):
    kind = "summary"  # or "detail"

    def get(self, request):
        form = self.get_form()
        if not form.is_valid():
            return HttpResponse("Invalid report filters: " + "; ".join(form.errors.get("__all__", [])), status=400)
        data = form.cleaned_data
        report = build_report(request.user, data)

        filename = f"vora-timetrack-{self.kind}-{data['group_by'] if self.kind == 'summary' else 'lines'}-{data['start']}-to-{data['end']}.csv"
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.write("﻿")  # byte-order mark: makes Excel read £ and accents correctly
        writer = csv.writer(response)
        if self.kind == "summary":
            self.write_summary(writer, report)
        else:
            self.write_detail(writer, report)
        return response

    def write_summary(self, writer, report):
        header = [report["group_label"], "Detail", "Entries", "Hours", "Billable hours", "Non-billable hours", "Billable %"]
        if report["show_costs"]:
            header += ["Approved value (GBP)", "Estimated value, not yet approved (GBP)", "Unpriced billable hours"]
        writer.writerow(header)
        for row in report["rows"] + [{**report["totals"], "label": "TOTAL", "sub": "", "entries": report["entry_count"]}]:
            line = [csv_safe(row["label"]), csv_safe(row["sub"]), row["entries"], row["hours"], row["billable"],
                    row["non_billable"], row["billable_percent"]]
            if report["show_costs"]:
                line += [row["approved_value"], row["estimated_value"], row["unpriced_hours"]]
            writer.writerow(line)

    def write_detail(self, writer, report):
        header = ["Date", "Week starting", "Person", "Business", "Project code", "Project", "Client", "Task",
                  "Hours", "Billable", "Timesheet status", "Description"]
        if report["show_costs"]:
            header[-1:-1] = ["Rate (GBP/h)", "Amount (GBP)", "Rate basis"]
        writer.writerow(header)
        for e in report["entries"]:
            project = e.task.project
            line = [e.work_date.isoformat(), e.timesheet.week_start.isoformat(), csv_safe(e.engineer),
                    csv_safe(project.business.name), csv_safe(project.code), csv_safe(project.name),
                    csv_safe(project.client_name), csv_safe(e.task.name), e.hours, "Yes" if e.is_billable else "No",
                    e.timesheet.get_status_display()]
            if report["show_costs"]:
                line += self.money_columns(e, report["book"])
            line.append(csv_safe(e.description))
            writer.writerow(line)

    @staticmethod
    def money_columns(entry, book):
        if not entry.is_billable:
            return ["", "", "Non-billable"]
        if entry.timesheet.status == "APPROVED":
            if entry.rate is None:
                return ["", "", "Approved - no rate found"]
            return [entry.rate, entry.amount, f"Fixed at approval ({csv_safe(entry.billing_rate.scope_label)})"]
        rate = book.find_for_entry(entry)
        if not rate:
            return ["", "", "Estimate - no rate found"]
        return [rate.hourly_rate, (entry.hours * rate.hourly_rate).quantize(Decimal("0.01")),
                f"Estimate ({csv_safe(rate.scope_label)})"]
