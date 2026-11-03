"""
Load FICTIONAL demo data for local development:

    python manage.py seed_demo

Creates two businesses, demo users for each role, sample projects/tasks,
SAMPLE billing rates and about two weeks of time entries. Nothing here is
real: names are invented and the rates are made-up round numbers.

The demo users' password is read from DEMO_USER_PASSWORD in your .env file,
so it never appears in the code or in Git. Refuses to run when DEBUG is off.
"""

import os
import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Business, User
from timetrack.models import BillingRate, Project, Task, TimeEntry, Timesheet, week_start

BUSINESSES = [("Vora Global Solutions", "VGS"), ("Vora Nexus", "VNX")]

# (business code, project code, name, billable, [(task, billable), ...])
PROJECTS = [
    ("VGS", "VGS-001", "Demo Project Alpha", True, [("Site survey", True), ("Design review", True), ("Travel", False)]),
    ("VGS", "VGS-002", "Demo Project Gamma", True, [("Installation", True), ("Commissioning", True)]),
    ("VGS", "VGS-INT", "Internal", False, [("Training", False), ("Admin", False)]),
    ("VNX", "VNX-001", "Demo Project Beta", True, [("Configuration", True), ("Testing", True)]),
    ("VNX", "VNX-002", "Demo Project Delta", True, [("Requirements", True), ("Support", True)]),
    ("VNX", "VNX-INT", "Internal", False, [("Training", False), ("Admin", False)]),
]

# (username, first, last, role, business code)
USERS = [
    ("demo.director", "Dana", "Sample", User.Role.DIRECTOR, None),
    ("vgs.manager", "Morgan", "Sample", User.Role.MANAGER, "VGS"),
    ("vgs.engineer1", "Avery", "Sample", User.Role.ENGINEER, "VGS"),
    ("vgs.engineer2", "Jordan", "Sample", User.Role.ENGINEER, "VGS"),
    ("vnx.manager", "Taylor", "Sample", User.Role.MANAGER, "VNX"),
    ("vnx.engineer1", "Riley", "Sample", User.Role.ENGINEER, "VNX"),
    ("vnx.engineer2", "Casey", "Sample", User.Role.ENGINEER, "VNX"),
]

# SAMPLE rates only - invented round numbers, not real Vora prices.
# (business, project code or None, engineer username or None, hourly rate)
SAMPLE_RATES = [
    ("VGS", None, None, "100.00"),
    ("VGS", "VGS-002", None, "120.00"),
    ("VGS", "VGS-001", "vgs.engineer1", "110.00"),
    ("VNX", None, None, "90.00"),
    ("VNX", "VNX-001", None, "95.00"),
]

DESCRIPTIONS = [
    "Sample work description",
    "Worked through checklist items (sample)",
    "Meeting and follow-up actions (sample)",
    "On-site work (sample)",
    "Documentation and notes (sample)",
]


class Command(BaseCommand):
    help = "Create fictional demo businesses, users, projects and time entries."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete demo users' time entries and timesheets first.")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DJANGO_DEBUG=True (never on a live site).")
        password = os.getenv("DEMO_USER_PASSWORD")
        if not password or len(password) < 10:
            raise CommandError("Set DEMO_USER_PASSWORD (at least 10 characters) in your .env file first.")

        businesses = {
            code: Business.objects.get_or_create(code=code, defaults={"name": name})[0]
            for name, code in BUSINESSES
        }

        for biz, code, name, billable, tasks in PROJECTS:
            project, _ = Project.objects.get_or_create(
                business=businesses[biz], code=code,
                defaults={"name": name, "is_billable": billable, "client_name": "Example Client" if billable else ""},
            )
            for task_name, task_billable in tasks:
                Task.objects.get_or_create(project=project, name=task_name, defaults={"is_billable": task_billable})

        users = []
        for username, first, last, role, biz in USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "role": role,
                          "business": businesses.get(biz), "email": f"{username}@example.com"},
            )
            if created:
                user.set_password(password)  # stored as a secure hash, never plain text
                user.save()
            users.append(user)

        self.make_rates(businesses, {u.username: u for u in users})

        if options["reset"]:
            # Bulk delete skips the locked-week check on purpose: this is a full demo reset.
            TimeEntry.objects.filter(engineer__in=users).delete()
            Timesheet.objects.filter(engineer__in=users).delete()
            # (Rates are kept: they're only re-created if missing.)

        created = 0
        new_entries_for = []
        for user in users:
            if user.business_id and not user.time_entries.exists():
                created += self.make_entries(user)
                new_entries_for.append(user.username)
        if new_entries_for:
            self.review_last_week({u.username: u for u in users}, new_entries_for)

        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready: {len(users)} users, {Project.objects.count()} projects, {created} new time entries."
        ))
        self.stdout.write("Sign in with any demo username (e.g. vgs.engineer1) and DEMO_USER_PASSWORD.")

    def make_rates(self, businesses, users):
        start = timezone.localdate().replace(month=1, day=1)
        for biz, project_code, username, amount in SAMPLE_RATES:
            project = Project.objects.get(business=businesses[biz], code=project_code) if project_code else None
            engineer = users[username] if username else None
            if not BillingRate.objects.filter(business=businesses[biz], project=project, engineer=engineer).exists():
                rate = BillingRate(business=businesses[biz], project=project, engineer=engineer,
                                   hourly_rate=Decimal(amount), effective_from=start,
                                   notes="Sample rate (not a real price)", authorised_by=users["demo.director"])
                rate.full_clean()
                rate.save()

    def review_last_week(self, users, fresh):
        """Give last week's demo timesheets a realistic mix of statuses."""
        last_monday = week_start(timezone.localdate()) - timedelta(days=7)
        plan = [
            # (engineer, reviewer, outcome, comment)
            ("vgs.engineer1", "vgs.manager", "approve", ""),
            ("vgs.engineer2", None, "submit", ""),
            ("vgs.manager", "demo.director", "approve", "Looks good (sample)."),
            ("vnx.engineer1", "vnx.manager", "reject", "Please move the travel time to its own task (sample)."),
            ("vnx.engineer2", None, "submit", ""),
            ("vnx.manager", None, "submit", ""),
        ]
        for engineer, reviewer, outcome, comment in plan:
            if engineer not in fresh:
                continue
            sheet = Timesheet.objects.filter(engineer=users[engineer], week_start=last_monday).first()
            if not sheet:
                continue
            sheet.submit(users[engineer])
            if outcome == "approve":
                sheet.approve(users[reviewer], comment)
            elif outcome == "reject":
                sheet.reject(users[reviewer], comment)

    def make_entries(self, user):
        """Weekday entries from last Monday up to today."""
        rng = random.Random(user.username)  # same 'random' data every time
        tasks = list(Task.objects.filter(project__business=user.business).select_related("project"))
        today = timezone.localdate()
        day = week_start(today) - timedelta(days=7)
        count = 0
        while day <= today:
            if day.weekday() < 5:
                daily = Decimal("4") if user.is_manager else Decimal(rng.choice(["7.5", "8"]))
                first = Decimal(rng.choice(["2", "3.5", "4", "5"])).min(daily)
                for hours in (first, daily - first):
                    if hours > 0:
                        # Roughly 4 in 5 entries go to billable work.
                        pool = [t for t in tasks if t.billable == (rng.random() < 0.8)] or tasks
                        entry = TimeEntry(engineer=user, work_date=day, task=rng.choice(pool),
                                          hours=hours, description=rng.choice(DESCRIPTIONS))
                        entry.full_clean()  # run the same validation as the web form
                        entry.save()
                        count += 1
            day += timedelta(days=1)
        return count
