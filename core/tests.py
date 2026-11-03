"""Automated tests for the core app. Run with: python manage.py test"""

from django.test import TestCase
from django.urls import reverse

from .sample_data import dashboard_summary


class PageTests(TestCase):
    def test_home_page_loads(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vora")

    def test_dashboard_loads_with_sample_data(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sample data only")
        self.assertContains(response, "Vora Nexus")


class SummaryTests(TestCase):
    def test_billable_and_non_billable_add_up(self):
        s = dashboard_summary()
        self.assertEqual(s["billable_hours"] + s["non_billable_hours"], s["total_hours"])

    def test_empty_entries_do_not_crash(self):
        s = dashboard_summary(entries=[])
        self.assertEqual(s["total_hours"], 0)
        self.assertEqual(s["billable_percent"], 0)
