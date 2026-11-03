"""
Tests for billing rates, pricing at approval, reports and CSV export.
Run with:  python manage.py test
"""

import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Business, User
from reports.views import csv_safe
from timetrack.billing import RateBook, price_entries, unpriced_approved_entries
from timetrack.models import BillingRate, Project, Task, TimeEntry, week_start

PASSWORD = "test-only-password-123"
D = Decimal


class BillingSetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.biz_a = Business.objects.create(name="Test Business A", code="TBA")
        cls.biz_b = Business.objects.create(name="Test Business B", code="TBB")

        def user(name, role, biz, first=""):
            return User.objects.create_user(name, password=PASSWORD, role=role, business=biz, first_name=first)

        cls.eng = user("eng", User.Role.ENGINEER, cls.biz_a, "Alpha")
        cls.eng2 = user("eng2", User.Role.ENGINEER, cls.biz_a, "Bravo")
        cls.mgr = user("mgr", User.Role.MANAGER, cls.biz_a)
        cls.eng_b = user("eng_b", User.Role.ENGINEER, cls.biz_b, "Charlie")
        cls.director = user("director", User.Role.DIRECTOR, None)

        cls.p1 = Project.objects.create(business=cls.biz_a, code="A-1", name="One")
        cls.p2 = Project.objects.create(business=cls.biz_a, code="A-2", name="Two")
        cls.internal = Project.objects.create(business=cls.biz_a, code="A-INT", name="Internal", is_billable=False)
        cls.pb = Project.objects.create(business=cls.biz_b, code="B-1", name="B One")
        cls.t1 = Task.objects.create(project=cls.p1, name="Build")
        cls.t2 = Task.objects.create(project=cls.p2, name="Test")
        cls.t_int = Task.objects.create(project=cls.internal, name="Training")
        cls.tb = Task.objects.create(project=cls.pb, name="Work")

        cls.monday = week_start(timezone.localdate()) - timedelta(days=7)
        cls.year_start = date(cls.monday.year - 1, 1, 1)

    def rate(self, amount, business=None, project=None, engineer=None, start=None, end=None):
        r = BillingRate(business=business or self.biz_a, project=project, engineer=engineer, hourly_rate=D(amount),
                        effective_from=start or self.year_start, effective_to=end, authorised_by=self.director)
        r.full_clean()
        r.save()
        return r

    def entry(self, task, hours, engineer=None, day=0, text="Work"):
        return TimeEntry.objects.create(engineer=engineer or self.eng, work_date=self.monday + timedelta(days=day),
                                        task=task, hours=D(hours), description=text)

    def approve(self, entry, reviewer=None):
        sheet = entry.timesheet
        sheet.submit(entry.engineer)
        sheet.approve(reviewer or (self.mgr if entry.engineer.business == self.biz_a else self.director))
        return sheet


class RateTests(BillingSetup):
    def test_most_specific_rate_wins(self):
        self.rate("100")
        self.rate("120", project=self.p1)
        self.rate("105", engineer=self.eng)
        self.rate("130", project=self.p1, engineer=self.eng)
        book = RateBook()
        day = self.monday

        def find(project, engineer):
            return book.find(business_id=self.biz_a.pk, project_id=project.pk, engineer_id=engineer.pk, day=day).hourly_rate

        self.assertEqual(find(self.p1, self.eng), D("130"))   # person on project
        self.assertEqual(find(self.p1, self.eng2), D("120"))  # anyone on project
        self.assertEqual(find(self.p2, self.eng), D("105"))   # person, any project
        self.assertEqual(find(self.p2, self.eng2), D("100"))  # business default

    def test_effective_dates(self):
        self.rate("100", end=self.monday - timedelta(days=1))
        self.rate("150", start=self.monday)
        book = RateBook()
        find = lambda d: book.find(business_id=self.biz_a.pk, project_id=self.p1.pk, engineer_id=self.eng.pk, day=d)
        self.assertEqual(find(self.monday - timedelta(days=1)).hourly_rate, D("100"))
        self.assertEqual(find(self.monday).hourly_rate, D("150"))

    def test_no_rate_for_other_business(self):
        self.rate("100", business=self.biz_b)
        self.assertIsNone(RateBook().find(business_id=self.biz_a.pk, project_id=self.p1.pk,
                                          engineer_id=self.eng.pk, day=self.monday))

    def test_overlapping_same_scope_rejected(self):
        self.rate("100")
        with self.assertRaises(ValidationError):
            self.rate("110", start=self.monday)
        self.rate("120", project=self.p1)  # different scope is fine

    def test_project_must_match_business(self):
        with self.assertRaises(ValidationError):
            self.rate("100", project=self.pb)


class PricingTests(BillingSetup):
    def test_approval_fixes_rate_on_billable_entries(self):
        self.rate("100")
        billable = self.entry(self.t1, "7.5")
        internal = self.entry(self.t_int, "2", day=1)
        self.approve(billable)
        billable.refresh_from_db()
        internal.refresh_from_db()
        self.assertEqual(billable.rate, D("100"))
        self.assertEqual(billable.amount, D("750.00"))
        self.assertIsNone(internal.rate)

    def test_later_rate_change_does_not_alter_approved(self):
        r = self.rate("100", end=self.monday + timedelta(days=30))
        e = self.entry(self.t1, "2")
        self.approve(e)
        self.rate("200", start=self.monday + timedelta(days=31))
        e.refresh_from_db()
        self.assertEqual(e.rate, D("100"))
        self.assertTrue(r.is_used)

    def test_reopen_clears_and_reapprove_reprices(self):
        self.rate("100")
        e = self.entry(self.t1, "2")
        sheet = self.approve(e)
        sheet.reopen(self.director, "Correction")
        e.refresh_from_db()
        self.assertIsNone(e.rate)

    def test_unpriced_then_price_missing(self):
        e = self.entry(self.t1, "3")
        self.approve(e)
        self.assertEqual(unpriced_approved_entries().count(), 1)
        self.rate("100")
        self.assertEqual(price_entries(unpriced_approved_entries(), only_missing=True), 1)
        e.refresh_from_db()
        self.assertEqual(e.rate, D("100"))

    def test_used_rate_cannot_be_ended_before_last_use(self):
        r = self.rate("100")
        e = self.entry(self.t1, "3", day=2)
        self.approve(e)
        r.effective_to = self.monday
        with self.assertRaises(ValidationError):
            r.full_clean()

    def test_used_rate_cannot_be_deleted(self):
        r = self.rate("100")
        self.approve(self.entry(self.t1, "3"))
        self.client.force_login(self.director)
        self.client.post(reverse("timetrack:rate_delete", args=[r.pk]))
        self.assertTrue(BillingRate.objects.filter(pk=r.pk).exists())


class RatePageTests(BillingSetup):
    def test_rates_are_director_only(self):
        for user in (self.eng, self.mgr):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("timetrack:rate_list")).status_code, 403)
            self.assertEqual(self.client.get(reverse("timetrack:rate_add")).status_code, 403)

    def test_director_adds_rate_and_is_recorded(self):
        self.client.force_login(self.director)
        response = self.client.post(reverse("timetrack:rate_add"), {
            "business": self.biz_a.pk, "hourly_rate": "99.50", "effective_from": self.year_start.isoformat(),
        })
        self.assertRedirects(response, reverse("timetrack:rate_list"))
        rate = BillingRate.objects.get()
        self.assertEqual(rate.authorised_by, self.director)

    def test_used_rate_price_cannot_change_via_form(self):
        r = self.rate("100")
        self.approve(self.entry(self.t1, "3"))
        self.client.force_login(self.director)
        self.client.post(reverse("timetrack:rate_edit", args=[r.pk]), {
            "business": self.biz_a.pk, "hourly_rate": "999", "effective_from": self.year_start.isoformat(),
            "notes": "changed",
        })
        r.refresh_from_db()
        self.assertEqual(r.hourly_rate, D("100"))  # disabled field ignored
        self.assertEqual(r.notes, "changed")


class ReportTests(BillingSetup):
    def setUp(self):
        self.rate("100")
        self.rate("120", project=self.p2)
        self.rate("80", business=self.biz_b)
        self.e1 = self.entry(self.t1, "5", text="Alpha p1")
        self.e2 = self.entry(self.t2, "2", day=1, text="Alpha p2")
        self.e3 = self.entry(self.t_int, "1", day=2, text="Alpha training")
        self.approve(self.e1)
        self.e4 = self.entry(self.t1, "4", engineer=self.eng2, text="Bravo draft")  # draft
        self.e5 = self.entry(self.tb, "6", engineer=self.eng_b, text="Charlie B")
        self.approve(self.e5, self.director)

    def params(self, **kw):
        p = {"start": (self.monday - timedelta(days=7)).isoformat(), "end": timezone.localdate().isoformat(),
             "group_by": "engineer", "status": "approved"}
        p.update(kw)
        return p

    def get(self, user, name="reports:report", **kw):
        self.client.force_login(user)
        return self.client.get(reverse(name), self.params(**kw))

    def read_csv(self, response):
        text = response.content.decode("utf-8-sig")
        return list(csv.reader(io.StringIO(text)))

    def test_director_sees_both_businesses_with_value(self):
        r = self.get(self.director).context["report"]
        self.assertEqual(r["totals"]["hours"], D("14"))  # approved: eng 8h + eng_b 6h
        # eng: 5h x 100 + 2h x 120 = 740 ; eng_b: 6h x 80 = 480
        self.assertEqual(r["totals"]["approved_value"], D("1220.00"))
        self.assertTrue(r["show_costs"])

    def test_manager_sees_own_business_without_money(self):
        response = self.get(self.mgr)
        r = response.context["report"]
        self.assertEqual(r["totals"]["hours"], D("8"))
        self.assertFalse(r["show_costs"])
        self.assertNotContains(response, "£")
        self.assertNotContains(response, "Charlie")

    def test_engineer_sees_only_own(self):
        r = self.get(self.eng2, status="all").context["report"]
        self.assertEqual(r["totals"]["hours"], D("4"))
        self.assertEqual(len(r["rows"]), 1)

    def test_status_all_includes_estimate(self):
        r = self.get(self.director, status="all", business=self.biz_a.pk).context["report"]
        self.assertEqual(r["totals"]["hours"], D("12"))
        self.assertEqual(r["totals"]["estimated_value"], D("400.00"))  # Bravo draft 4h x 100

    def test_group_by_project_and_filters(self):
        r = self.get(self.director, group_by="project", project=self.p1.pk, status="all").context["report"]
        self.assertEqual([row["label"] for row in r["rows"]], ["A-1 · One"])
        self.assertEqual(r["rows"][0]["hours"], D("9"))

    def test_group_by_business(self):
        r = self.get(self.director, group_by="business").context["report"]
        self.assertEqual({row["label"] for row in r["rows"]}, {"Test Business A", "Test Business B"})

    def test_billable_split(self):
        r = self.get(self.eng, status="all", group_by="task").context["report"]
        self.assertEqual(r["totals"]["billable"], D("7"))
        self.assertEqual(r["totals"]["non_billable"], D("1"))

    def test_invalid_range(self):
        response = self.get(self.director, start="2026-05-01", end="2026-04-01")
        self.assertNotIn("report", response.context)
        self.assertContains(response, "must be on or after")

    def test_summary_csv_for_director(self):
        response = self.get(self.director, "reports:export_summary", group_by="business")
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        rows = self.read_csv(response)
        self.assertIn("Approved value (GBP)", rows[0])
        self.assertEqual(rows[-1][0], "TOTAL")
        self.assertEqual(rows[-1][7], "1220.00")

    def test_detail_csv_for_manager_has_no_money(self):
        rows = self.read_csv(self.get(self.mgr, "reports:export_detail", status="all"))
        self.assertNotIn("Rate (GBP/h)", rows[0])
        self.assertEqual(len(rows) - 1, 4)  # Alpha x3 + Bravo; nothing from business B
        self.assertNotIn("Charlie", str(rows))

    def test_csv_injection_neutralised(self):
        TimeEntry.objects.create(engineer=self.eng, work_date=timezone.localdate(), task=self.t1,
                                 hours=D("1"), description="=HYPERLINK(\"http://evil\")")
        rows = self.read_csv(self.get(self.eng, "reports:export_detail", status="all"))
        descriptions = [r[-1] for r in rows[1:]]
        self.assertIn("'=HYPERLINK(\"http://evil\")", descriptions)
        self.assertEqual(csv_safe("-5"), "'-5")
        self.assertEqual(csv_safe("Normal"), "Normal")

    def test_reports_need_login(self):
        response = self.client.get(reverse("reports:export_detail"))
        self.assertEqual(response.status_code, 302)
