"""
The report engine: turns filters into grouped totals.

Both the web page and the CSV exports call build_report(), so the numbers
on screen and in the spreadsheet always match.

Money figures (only for users allowed by billing.can_see_costs):
  * Approved value   = hours x the rate fixed when the week was approved.
  * Estimated value  = for weeks NOT approved yet: hours x today's rate for
                       that date. It can still change, so it's kept separate.
  * Unpriced hours   = approved billable hours that had no matching rate.
"""

from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from timetrack.access import visible_entries
from timetrack.billing import RateBook, can_see_costs
from timetrack.models import Timesheet

ZERO = Decimal("0")

STATUS_FILTERS = {
    "approved": ("Approved only", [Timesheet.Status.APPROVED]),
    "submitted": ("Submitted and approved", [Timesheet.Status.SUBMITTED, Timesheet.Status.APPROVED]),
    "all": ("All, including drafts", None),
}

GROUPINGS = OrderedDict(
    [
        ("engineer", "Person"),
        ("project", "Project"),
        ("business", "Business"),
        ("task", "Task"),
        ("week", "Week"),
    ]
)


def group_key(entry, group_by):
    """(sort key, label, sub-label) for the group an entry belongs to."""
    project = entry.task.project
    if group_by == "engineer":
        return (str(entry.engineer).lower(), str(entry.engineer), entry.engineer.business.code if entry.engineer.business else "")
    if group_by == "project":
        return ((project.business.code, project.code), f"{project.code} · {project.name}", project.client_name or project.business.name)
    if group_by == "business":
        return (project.business.name, project.business.name, "")
    if group_by == "task":
        return ((project.code, entry.task.name), f"{project.code} › {entry.task.name}", project.name)
    monday = entry.timesheet.week_start
    return (monday, f"Week of {monday:%d %b %Y}", f"{monday:%a %d %b} – {monday + timedelta(days=6):%a %d %b}")


def filtered_entries(user, data):
    """The entries a report covers: the user's scope, narrowed by the form's filters."""
    qs = visible_entries(user).select_related(
        "engineer__business", "task__project__business", "timesheet", "billing_rate"
    ).filter(work_date__gte=data["start"], work_date__lte=data["end"])
    statuses = STATUS_FILTERS[data["status"]][1]
    if statuses:
        qs = qs.filter(timesheet__status__in=statuses)
    if data.get("business"):
        qs = qs.filter(task__project__business=data["business"])
    if data.get("project"):
        qs = qs.filter(task__project=data["project"])
    if data.get("engineer"):
        qs = qs.filter(engineer=data["engineer"])
    return qs.order_by("work_date", "engineer__first_name", "pk")


def entry_value(entry, book):
    """(approved value, estimated value, unpriced hours) for one entry."""
    if not entry.is_billable:
        return ZERO, ZERO, ZERO
    if entry.timesheet.status == Timesheet.Status.APPROVED:
        if entry.rate is None:
            return ZERO, ZERO, entry.hours
        return entry.amount, ZERO, ZERO
    rate = book.find_for_entry(entry)
    estimate = (entry.hours * rate.hourly_rate).quantize(Decimal("0.01")) if rate else ZERO
    return ZERO, estimate, ZERO


def build_report(user, data):
    show_costs = can_see_costs(user)
    entries = list(filtered_entries(user, data))
    book = RateBook({e.task.project.business_id for e in entries}) if show_costs else None

    groups = {}
    totals = {"hours": ZERO, "billable": ZERO, "approved_value": ZERO, "estimated_value": ZERO, "unpriced_hours": ZERO}
    for entry in entries:
        sort_key, label, sub = group_key(entry, data["group_by"])
        row = groups.setdefault(sort_key, {"label": label, "sub": sub, "entries": 0, **{k: ZERO for k in totals}})
        values = {"hours": entry.hours, "billable": entry.hours if entry.is_billable else ZERO}
        if show_costs:
            values["approved_value"], values["estimated_value"], values["unpriced_hours"] = entry_value(entry, book)
        row["entries"] += 1
        for key, value in values.items():
            row[key] += value
            totals[key] += value

    rows = [groups[k] for k in sorted(groups)]
    for row in rows + [totals]:
        row["non_billable"] = row["hours"] - row["billable"]
        row["billable_percent"] = round(row["billable"] / row["hours"] * 100) if row["hours"] else 0
        row["share"] = round(row["hours"] / totals["hours"] * 100) if totals["hours"] else 0

    return {
        "rows": rows,
        "totals": totals,
        "entries": entries,
        "entry_count": len(entries),
        "show_costs": show_costs,
        "book": book,
        "group_label": GROUPINGS[data["group_by"]],
        "status_label": STATUS_FILTERS[data["status"]][0],
        "includes_unapproved": data["status"] != "approved",
    }
