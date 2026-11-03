"""
Billing logic: finding the right authorised rate and pricing approved hours.

RateBook loads the rates ONCE and answers many lookups from memory, so a
report covering thousands of entries doesn't run thousands of queries.
"""

from django.db import transaction

from .models import BillingRate, TimeEntry


def can_see_costs(user):
    """Who may see rates and money figures. Change this one line to widen access
    (for example: `return user.is_director or user.is_manager`)."""
    return user.is_authenticated and user.is_director


class RateBook:
    def __init__(self, business_ids=None):
        rates = BillingRate.objects.all()
        if business_ids is not None:
            rates = rates.filter(business_id__in=business_ids)
        self.by_business = {}
        for rate in rates:
            self.by_business.setdefault(rate.business_id, []).append(rate)

    def find(self, *, business_id, project_id, engineer_id, day):
        """The most specific rate in force on `day`, or None if there isn't one."""
        best, best_score = None, 0
        for rate in self.by_business.get(business_id, []):
            if not rate.is_active_on(day):
                continue
            if rate.project_id not in (None, project_id) or rate.engineer_id not in (None, engineer_id):
                continue  # a rate for a different project or person
            # More specific = higher score: project counts more than engineer.
            score = 1 + (2 if rate.project_id else 0) + (1 if rate.engineer_id else 0)
            if score > best_score:
                best, best_score = rate, score
        return best

    def find_for_entry(self, entry):
        project = entry.task.project
        return self.find(
            business_id=project.business_id, project_id=project.pk, engineer_id=entry.engineer_id, day=entry.work_date
        )


@transaction.atomic
def price_entries(entries, only_missing=False):
    """Copy the rate in force onto each billable entry. Returns how many got a rate."""
    entries = list(entries.select_related("task__project"))
    if only_missing:
        entries = [e for e in entries if e.rate is None]
    book = RateBook({e.task.project.business_id for e in entries})
    priced = 0
    for entry in entries:
        rate = book.find_for_entry(entry) if entry.is_billable else None
        entry.billing_rate = rate
        entry.rate = rate.hourly_rate if rate else None
        priced += rate is not None
    # bulk_update writes all rows in one query and skips TimeEntry.save()/clean(),
    # which is what we want: these entries are in a locked (approved) week.
    TimeEntry.objects.bulk_update(entries, ["rate", "billing_rate"])
    return priced


def unprice_entries(entries):
    entries.update(rate=None, billing_rate=None)


def unpriced_approved_entries(queryset=None):
    """Approved, billable hours that have no rate (no rate existed when approved)."""
    qs = queryset if queryset is not None else TimeEntry.objects.all()
    return qs.filter(timesheet__status="APPROVED", is_billable=True, rate__isnull=True)
