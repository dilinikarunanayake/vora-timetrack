"""
Time tracking data: projects, tasks and time entries.

Relationships:
    Business 1 ──< Project 1 ──< Task 1 ──< TimeEntry >── 1 User (engineer)
                                             TimeEntry >── 1 Timesheet (one per engineer per week)

A time entry points at a TASK; the project is reached through task.project.
Storing the project only once avoids the two ever disagreeing.

Every entry belongs to the weekly Timesheet for its engineer and week.
The timesheet's STATUS decides whether the week's entries can still change:

    DRAFT ──submit──> SUBMITTED ──approve──> APPROVED   (locked)
      ^                 │    │
      └──withdraw───────┘    └──reject──> REJECTED ──submit──> SUBMITTED
      ^                                      (editable again)
      └──────────reopen (director only)─── APPROVED

BILLING: a BillingRate is an authorised hourly price, valid between two dates.
When a timesheet is APPROVED, each billable entry is "priced": the rate in
force on that day is copied onto the entry (TimeEntry.rate). Like a line on an
invoice, that price then never changes, even if rates are updated later.
Reopening a week clears the prices; approving again re-prices it.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.models import Business

MAX_HOURS_PER_DAY = Decimal("24")


class TimeStampedModel(models.Model):
    """Abstract base: adds created/updated timestamps to any model that inherits it."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True  # no table of its own


class Project(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="projects")
    code = models.CharField(max_length=20, help_text="Short reference, e.g. VGS-001")
    name = models.CharField(max_length=150)
    client_name = models.CharField(max_length=150, blank=True)
    is_billable = models.BooleanField(
        default=True, help_text="Untick for internal projects (training, admin)."
    )
    is_active = models.BooleanField(default=True, help_text="Inactive projects can't receive new time.")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["business__name", "code"]
        constraints = [
            # The same code can't be used twice within one business.
            models.UniqueConstraint(fields=["business", "code"], name="unique_project_code_per_business"),
        ]

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date can't be before the start date."})

    def __str__(self):
        return f"{self.code} · {self.name}"


class Task(TimeStampedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    name = models.CharField(max_length=150)
    is_billable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["project__code", "name"]
        constraints = [
            models.UniqueConstraint(fields=["project", "name"], name="unique_task_name_per_project"),
        ]

    @property
    def billable(self):
        """Time is billable only if BOTH the project and the task are billable."""
        return self.is_billable and self.project.is_billable

    def __str__(self):
        return f"{self.project.code} · {self.name}"


class Timesheet(TimeStampedModel):
    """One engineer's time for one week (Monday to Sunday)."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    EDITABLE = {Status.DRAFT, Status.REJECTED}

    engineer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="timesheets")
    week_start = models.DateField(help_text="Always a Monday.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(blank=True, max_length=1000)

    class Meta:
        ordering = ["-week_start", "engineer__username"]
        constraints = [
            models.UniqueConstraint(fields=["engineer", "week_start"], name="one_timesheet_per_engineer_week"),
        ]

    def clean(self):
        if self.week_start and self.week_start.weekday() != 0:
            raise ValidationError({"week_start": "A timesheet week must start on a Monday."})

    def __str__(self):
        return f"{self.engineer} · week of {self.week_start:%d %b %Y}"

    # --- Handy read-only properties ------------------------------------------

    @property
    def week_end(self):
        return self.week_start + timedelta(days=6)

    @property
    def is_editable(self):
        return self.status in self.EDITABLE

    @property
    def is_locked(self):
        return not self.is_editable

    def totals(self):
        t = self.entries.aggregate(total=Sum("hours"), billable=Sum("hours", filter=models.Q(is_billable=True)))
        total, billable = t["total"] or Decimal("0"), t["billable"] or Decimal("0")
        return {"total": total, "billable": billable, "non_billable": total - billable}

    # --- Who may do what ------------------------------------------------------

    def can_review(self, user):
        """Managers review their own business; directors review anyone. Nobody reviews themselves."""
        if not user.is_authenticated or user.pk == self.engineer_id:
            return False
        return user.is_director or (user.is_manager and user.business_id == self.engineer.business_id)

    # --- Status changes -------------------------------------------------------
    # Each change runs inside a database transaction and re-reads the row with a
    # lock (select_for_update), so two managers clicking at the same moment
    # can't both act on the same timesheet.

    def _change_status(self, by, action, allowed_from, new_status, comment=""):
        with transaction.atomic():
            current = Timesheet.objects.select_for_update().get(pk=self.pk)
            if current.status not in allowed_from:
                raise ValidationError(
                    f"This timesheet is {current.get_status_display().lower()}, so it can't be {action.label.lower()}."
                )
            self.status = new_status
            now = timezone.now()
            if action == TimesheetAction.Action.SUBMITTED:
                self.submitted_at = now
                self.reviewed_by, self.reviewed_at, self.review_comment = None, None, ""
            elif action in (TimesheetAction.Action.APPROVED, TimesheetAction.Action.REJECTED):
                self.reviewed_by, self.reviewed_at, self.review_comment = by, now, comment
            elif action == TimesheetAction.Action.REOPENED:
                self.review_comment = comment
            self.save()
            TimesheetAction.objects.create(timesheet=self, action=action, by=by, comment=comment)

            # Fix the price of approved hours; unfix it when a week is reopened.
            from .billing import price_entries, unprice_entries  # imported here to avoid a circular import

            if new_status == self.Status.APPROVED:
                price_entries(self.entries.all())
            elif action == TimesheetAction.Action.REOPENED:
                unprice_entries(self.entries.all())

    def submit(self, by):
        if by.pk != self.engineer_id:
            raise PermissionDenied("You can only submit your own timesheet.")
        if self.week_start > timezone.localdate():
            raise ValidationError("You can't submit a week that hasn't started yet.")
        if not self.entries.exists():
            raise ValidationError("There are no time entries in this week to submit.")
        self._change_status(by, TimesheetAction.Action.SUBMITTED, self.EDITABLE, self.Status.SUBMITTED)

    def withdraw(self, by):
        """The engineer pulls a submitted week back to draft before it is reviewed."""
        if by.pk != self.engineer_id:
            raise PermissionDenied("You can only withdraw your own timesheet.")
        self._change_status(by, TimesheetAction.Action.WITHDRAWN, {self.Status.SUBMITTED}, self.Status.DRAFT)

    def approve(self, by, comment=""):
        if not self.can_review(by):
            raise PermissionDenied("You can't review this timesheet.")
        self._change_status(by, TimesheetAction.Action.APPROVED, {self.Status.SUBMITTED}, self.Status.APPROVED, comment)

    def reject(self, by, comment):
        if not self.can_review(by):
            raise PermissionDenied("You can't review this timesheet.")
        if not comment.strip():
            raise ValidationError("Please give a reason so the engineer knows what to fix.")
        self._change_status(by, TimesheetAction.Action.REJECTED, {self.Status.SUBMITTED}, self.Status.REJECTED, comment)

    def reopen(self, by, comment):
        """Unlock an approved week for corrections. Directors only, reason required."""
        if not (by.is_director and by.pk != self.engineer_id):
            raise PermissionDenied("Only a director can reopen an approved timesheet.")
        if not comment.strip():
            raise ValidationError("Please give a reason for reopening this week.")
        self._change_status(by, TimesheetAction.Action.REOPENED, {self.Status.APPROVED}, self.Status.DRAFT, comment)


class TimesheetAction(models.Model):
    """Audit trail: every submit / approve / reject / reopen, who did it and when."""

    class Action(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        REOPENED = "REOPENED", "Reopened"

    timesheet = models.ForeignKey(Timesheet, on_delete=models.CASCADE, related_name="actions")
    action = models.CharField(max_length=10, choices=Action.choices)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    at = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["at", "pk"]

    def __str__(self):
        return f"{self.get_action_display()} by {self.by} at {self.at:%d %b %Y %H:%M}"


class BillingRate(models.Model):
    """
    An authorised hourly billing rate. The most specific rate wins:

        1. this engineer on this project
        2. anyone on this project
        3. this engineer on any project in the business
        4. the business default (no project, no engineer)

    Rates are effective-dated. To change a price, end the old rate (set
    "effective to") and add a new one, so history stays accurate.
    """

    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="billing_rates")
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, null=True, blank=True, related_name="billing_rates",
        help_text="Leave empty to apply to every project in the business.",
    )
    engineer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="billing_rates",
        help_text="Leave empty to apply to everyone.",
    )
    hourly_rate = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))],
        help_text=f"Per hour, in {settings.BILLING_CURRENCY}.",
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True, help_text="Leave empty if the rate has no end date.")
    notes = models.CharField(max_length=200, blank=True)
    # Who last saved (authorised) this rate, and when.
    authorised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    authorised_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["business__name", "project__code", "engineer__first_name", "-effective_from"]

    @property
    def scope_label(self):
        if self.project_id and self.engineer_id:
            return f"{self.engineer} on {self.project.code}"
        if self.project_id:
            return f"Anyone on {self.project.code}"
        if self.engineer_id:
            return f"{self.engineer}, any project"
        return "Business default"

    def is_active_on(self, day):
        return self.effective_from <= day and (self.effective_to is None or day <= self.effective_to)

    @property
    def is_used(self):
        """True once any approved hours have been priced with this rate."""
        return self.pk is not None and self.priced_entries.exists()

    def clean(self):
        errors = {}
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            errors["effective_to"] = "The end date can't be before the start date."
        if self.business_id and self.project_id and self.project.business_id != self.business_id:
            errors["project"] = "This project belongs to a different business."
        if self.business_id and self.engineer_id and self.engineer.business_id != self.business_id:
            errors["engineer"] = "This person belongs to a different business."
        if self.is_used and self.effective_to:
            last_used = self.priced_entries.aggregate(last=models.Max("work_date"))["last"]
            if self.effective_to < last_used:
                errors["effective_to"] = f"Approved hours up to {last_used:%d %b %Y} use this rate; end it on or after that date."
        if errors:
            raise ValidationError(errors)

        # Two rates for exactly the same scope must not overlap in time.
        if self.business_id and self.effective_from:
            same_scope = BillingRate.objects.filter(
                business_id=self.business_id, project_id=self.project_id, engineer_id=self.engineer_id
            ).exclude(pk=self.pk)
            far_future = date.max
            for other in same_scope:
                if self.effective_from <= (other.effective_to or far_future) and other.effective_from <= (
                    self.effective_to or far_future
                ):
                    raise ValidationError(
                        f"This overlaps an existing rate for the same scope "
                        f"({other.effective_from:%d %b %Y} to "
                        f"{other.effective_to.strftime('%d %b %Y') if other.effective_to else 'open-ended'}). "
                        "End that rate first."
                    )

    def __str__(self):
        return f"{self.business.code} · {self.scope_label} · {self.hourly_rate}/h from {self.effective_from}"


class TimeEntry(TimeStampedModel):
    engineer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="time_entries"
    )
    work_date = models.DateField()
    task = models.ForeignKey(Task, on_delete=models.PROTECT, related_name="time_entries")
    hours = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.25")), MaxValueValidator(MAX_HOURS_PER_DAY)],
        help_text="In quarter hours, e.g. 7.5",
    )
    description = models.TextField(max_length=1000)
    # Copied from the task when saved, so history stays correct even if the
    # task's billable setting changes later.
    is_billable = models.BooleanField(editable=False, default=True)
    # Set automatically from engineer + work date when saved.
    timesheet = models.ForeignKey(Timesheet, on_delete=models.PROTECT, related_name="entries", editable=False)
    # Filled in when the week is APPROVED (billable entries only). See billing.py.
    rate = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, editable=False)
    billing_rate = models.ForeignKey(
        BillingRate, on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="priced_entries"
    )

    class Meta:
        ordering = ["-work_date", "-created_at"]
        verbose_name_plural = "time entries"
        indexes = [models.Index(fields=["engineer", "work_date"])]

    @property
    def project(self):
        return self.task.project

    @property
    def is_locked(self):
        return self.timesheet_id is not None and self.timesheet.is_locked

    @property
    def amount(self):
        """Billable value of this entry once priced, otherwise None."""
        return (self.hours * self.rate).quantize(Decimal("0.01")) if self.rate is not None else None

    def check_not_locked(self):
        """Raise an error if this entry sits in a submitted or approved week."""
        if self.pk:
            original = TimeEntry.objects.select_related("timesheet").get(pk=self.pk)
            if original.timesheet.is_locked:
                raise ValidationError(
                    f"The week of {original.timesheet.week_start:%d %b %Y} is "
                    f"{original.timesheet.get_status_display().lower()} and locked."
                )

    def clean(self):
        errors = {}
        today = timezone.localdate()

        # Locking: the entry's current week AND the week it's moving to must be editable.
        self.check_not_locked()
        if self.engineer_id and self.work_date:
            target = Timesheet.objects.filter(engineer_id=self.engineer_id, week_start=week_start(self.work_date)).first()
            if target and target.is_locked:
                errors["work_date"] = (
                    f"The week of {target.week_start:%d %b %Y} is {target.get_status_display().lower()} "
                    "and locked. Ask your manager if something needs changing."
                )

        if self.work_date and self.work_date > today:
            errors["work_date"] = "You can't log time for a future date."

        if self.hours is not None and (self.hours * 4) % 1 != 0:
            errors["hours"] = "Use quarter hours: .00, .25, .50 or .75."

        if self.task_id:
            project = self.task.project
            if not (self.task.is_active and project.is_active):
                errors["task"] = "This task or project is closed for new time."
            elif self.engineer_id and project.business_id != self.engineer.business_id:
                errors["task"] = "This project belongs to a different business."
            elif self.work_date and project.start_date and self.work_date < project.start_date:
                errors["work_date"] = "This date is before the project started."
            elif self.work_date and project.end_date and self.work_date > project.end_date:
                errors["work_date"] = "This date is after the project ended."

        # No more than 24 hours in one day across all of the engineer's entries.
        if self.engineer_id and self.work_date and self.hours and "hours" not in errors:
            other = (
                TimeEntry.objects.filter(engineer_id=self.engineer_id, work_date=self.work_date)
                .exclude(pk=self.pk)
                .aggregate(total=Sum("hours"))["total"]
                or Decimal("0")
            )
            if other + self.hours > MAX_HOURS_PER_DAY:
                errors["hours"] = f"That would make {other + self.hours} hours on this day (maximum 24)."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.is_billable = self.task.billable
        self.timesheet, _ = Timesheet.objects.get_or_create(
            engineer_id=self.engineer_id, week_start=week_start(self.work_date)
        )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.check_not_locked()
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.engineer} · {self.work_date} · {self.hours}h"


def week_start(day):
    """Monday of the week containing `day`."""
    return day - timedelta(days=day.weekday())
