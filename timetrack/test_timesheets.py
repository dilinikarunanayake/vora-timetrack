"""
Tests for weekly timesheets: status changes, who may do them, and locking.
Run with:  python manage.py test
"""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Business, User
from timetrack.models import Project, Task, TimeEntry, Timesheet, TimesheetAction, week_start

PASSWORD = "test-only-password-123"
S = Timesheet.Status


class TimesheetSetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        a = Business.objects.create(name="Test Business A", code="TBA")
        b = Business.objects.create(name="Test Business B", code="TBB")

        def user(name, role, biz):
            return User.objects.create_user(name, password=PASSWORD, role=role, business=biz)

        cls.eng = user("eng", User.Role.ENGINEER, a)
        cls.eng2 = user("eng2", User.Role.ENGINEER, a)
        cls.mgr = user("mgr", User.Role.MANAGER, a)
        cls.mgr_b = user("mgr_b", User.Role.MANAGER, b)
        cls.director = user("director", User.Role.DIRECTOR, None)

        project = Project.objects.create(business=a, code="A-1", name="Project A")
        cls.task = Task.objects.create(project=project, name="Build")

        cls.last_monday = week_start(timezone.localdate()) - timedelta(days=7)
        cls.wednesday = cls.last_monday + timedelta(days=2)

    def setUp(self):
        self.entry = TimeEntry.objects.create(
            engineer=self.eng, work_date=self.wednesday, task=self.task, hours=Decimal("7.5"), description="Work"
        )
        self.sheet = self.entry.timesheet

    def new_entry(self, **kw):
        data = {"engineer": self.eng, "work_date": self.wednesday, "task": self.task,
                "hours": Decimal("1"), "description": "More"}
        data.update(kw)
        return TimeEntry(**data)


class TimesheetModelTests(TimesheetSetup):
    def test_entry_creates_weekly_timesheet(self):
        self.assertEqual(self.sheet.engineer, self.eng)
        self.assertEqual(self.sheet.week_start, self.last_monday)
        self.assertEqual(self.sheet.status, S.DRAFT)
        # A second entry in the same week joins the same timesheet.
        e2 = self.new_entry(work_date=self.last_monday)
        e2.save()
        self.assertEqual(e2.timesheet, self.sheet)

    def test_full_approve_flow_with_audit_trail(self):
        self.sheet.submit(self.eng)
        self.assertEqual(self.sheet.status, S.SUBMITTED)
        self.assertIsNotNone(self.sheet.submitted_at)
        self.sheet.approve(self.mgr, "OK")
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.status, S.APPROVED)
        self.assertEqual(self.sheet.reviewed_by, self.mgr)
        actions = list(self.sheet.actions.values_list("action", flat=True))
        self.assertEqual(actions, [TimesheetAction.Action.SUBMITTED, TimesheetAction.Action.APPROVED])

    def test_reject_needs_comment_then_resubmit(self):
        self.sheet.submit(self.eng)
        with self.assertRaises(ValidationError):
            self.sheet.reject(self.mgr, "   ")
        self.sheet.reject(self.mgr, "Fix Wednesday")
        self.assertEqual(self.sheet.status, S.REJECTED)
        self.assertTrue(self.sheet.is_editable)
        self.sheet.submit(self.eng)  # resubmitting is allowed
        self.assertEqual(self.sheet.status, S.SUBMITTED)
        self.assertEqual(self.sheet.review_comment, "")

    def test_withdraw(self):
        self.sheet.submit(self.eng)
        self.sheet.withdraw(self.eng)
        self.assertEqual(self.sheet.status, S.DRAFT)

    def test_invalid_transitions(self):
        with self.assertRaises(ValidationError):
            self.sheet.approve(self.mgr)  # still a draft
        self.sheet.submit(self.eng)
        with self.assertRaises(ValidationError):
            self.sheet.submit(self.eng)  # already submitted

    def test_cannot_submit_empty_or_future_week(self):
        empty = Timesheet.objects.create(engineer=self.eng, week_start=self.last_monday - timedelta(days=7))
        with self.assertRaises(ValidationError):
            empty.submit(self.eng)
        future = Timesheet.objects.create(engineer=self.eng, week_start=week_start(timezone.localdate()) + timedelta(days=7))
        with self.assertRaises(ValidationError):
            future.submit(self.eng)

    def test_review_permissions(self):
        self.sheet.submit(self.eng)
        for not_allowed in (self.eng, self.eng2, self.mgr_b):
            with self.assertRaises(PermissionDenied):
                self.sheet.approve(not_allowed)
        self.assertTrue(self.sheet.can_review(self.director))

    def test_nobody_reviews_themselves(self):
        own = TimeEntry.objects.create(engineer=self.mgr, work_date=self.wednesday, task=self.task,
                                       hours=Decimal("4"), description="Mgr work").timesheet
        own.submit(self.mgr)
        with self.assertRaises(PermissionDenied):
            own.approve(self.mgr)
        own.approve(self.director)  # a director can

    def test_only_owner_submits(self):
        with self.assertRaises(PermissionDenied):
            self.sheet.submit(self.mgr)

    def test_reopen_director_only_with_reason(self):
        self.sheet.submit(self.eng)
        self.sheet.approve(self.mgr)
        with self.assertRaises(PermissionDenied):
            self.sheet.reopen(self.mgr, "Need change")
        with self.assertRaises(ValidationError):
            self.sheet.reopen(self.director, "")
        self.sheet.reopen(self.director, "Client asked for a correction")
        self.assertEqual(self.sheet.status, S.DRAFT)


class LockingTests(TimesheetSetup):
    def lock(self, approve=True):
        self.sheet.submit(self.eng)
        if approve:
            self.sheet.approve(self.mgr)

    def test_cannot_add_to_locked_week(self):
        for approve in (False, True):  # submitted and approved both lock
            with self.subTest(approved=approve):
                if approve:
                    self.sheet.withdraw(self.eng)
                self.lock(approve)
                with self.assertRaises(ValidationError):
                    self.new_entry().full_clean()

    def test_cannot_edit_or_move_locked_entry(self):
        self.lock()
        self.entry.hours = Decimal("8")
        with self.assertRaises(ValidationError):
            self.entry.full_clean()
        self.entry.work_date = self.wednesday - timedelta(days=7)
        with self.assertRaises(ValidationError):
            self.entry.full_clean()

    def test_cannot_move_entry_into_locked_week(self):
        other = TimeEntry.objects.create(engineer=self.eng, work_date=timezone.localdate(), task=self.task,
                                         hours=Decimal("1"), description="This week")
        self.lock()
        other.work_date = self.wednesday
        with self.assertRaises(ValidationError):
            other.full_clean()

    def test_cannot_delete_locked_entry(self):
        self.lock()
        with self.assertRaises(ValidationError):
            self.entry.delete()
        self.assertTrue(TimeEntry.objects.filter(pk=self.entry.pk).exists())

    def test_rejected_week_is_editable(self):
        self.sheet.submit(self.eng)
        self.sheet.reject(self.mgr, "Fix it")
        self.new_entry().full_clean()  # no error

    def test_other_engineers_week_unaffected(self):
        self.lock()
        TimeEntry(engineer=self.eng2, work_date=self.wednesday, task=self.task,
                  hours=Decimal("1"), description="x").full_clean()  # no error


class TimesheetPageTests(TimesheetSetup):
    def action(self, user, action, comment="", sheet=None):
        self.client.force_login(user)
        url = reverse("timetrack:timesheet_action", args=[(sheet or self.sheet).pk, action])
        return self.client.post(url, {"comment": comment})

    def test_week_page_shows_entries(self):
        self.client.force_login(self.eng)
        response = self.client.get(reverse("timetrack:my_week", args=[self.last_monday.isoformat()]))
        self.assertContains(response, "Work")
        self.assertContains(response, "Submit 7.50 hours")

    def test_week_page_redirects_to_monday(self):
        self.client.force_login(self.eng)
        response = self.client.get(reverse("timetrack:my_week", args=[self.wednesday.isoformat()]))
        self.assertRedirects(response, reverse("timetrack:my_week", args=[self.last_monday.isoformat()]))

    def test_submit_and_approve_through_pages(self):
        self.action(self.eng, "submit")
        self.client.force_login(self.mgr)
        approvals = self.client.get(reverse("timetrack:approvals"))
        self.assertContains(approvals, "eng")
        self.action(self.mgr, "approve")
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.status, S.APPROVED)

    def test_reject_without_comment_shows_error(self):
        self.action(self.eng, "submit")
        response = self.action(self.mgr, "reject", comment="")
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.status, S.SUBMITTED)
        self.assertEqual(response.status_code, 302)

    def test_engineer_cannot_approve(self):
        self.action(self.eng, "submit")
        self.assertEqual(self.action(self.eng2, "approve").status_code, 404)  # not even visible
        self.assertEqual(self.action(self.eng, "approve").status_code, 403)   # own: visible, not allowed

    def test_other_business_manager_gets_404(self):
        self.action(self.eng, "submit")
        self.assertEqual(self.action(self.mgr_b, "approve").status_code, 404)

    def test_actions_require_post(self):
        self.client.force_login(self.eng)
        url = reverse("timetrack:timesheet_action", args=[self.sheet.pk, "submit"])
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_locked_entry_edit_page_redirects(self):
        self.action(self.eng, "submit")
        self.client.force_login(self.eng)
        response = self.client.get(reverse("timetrack:entry_edit", args=[self.entry.pk]))
        self.assertRedirects(response, reverse("timetrack:entry_list"))

    def test_unsafe_next_url_ignored(self):
        self.client.force_login(self.eng)
        response = self.client.post(
            reverse("timetrack:entry_add") + "?next=https://evil.example.com/",
            {"work_date": timezone.localdate().isoformat(), "task": self.task.pk, "hours": "1",
             "description": "x", "next": "https://evil.example.com/"},
        )
        self.assertRedirects(response, reverse("timetrack:entry_list"))

    def test_approvals_badge_in_menu(self):
        self.action(self.eng, "submit")
        self.client.force_login(self.mgr)
        response = self.client.get(reverse("timetrack:dashboard"))
        self.assertContains(response, 'text-bg-danger">1</span>')
