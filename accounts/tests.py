"""Tests for sign-in protection. Run with: python manage.py test"""

from axes.models import AccessAttempt
from django.test import TestCase
from django.urls import reverse

from accounts.models import Business, User

PASSWORD = "test-only-password-123"


class LockoutTests(TestCase):
    def setUp(self):
        biz = Business.objects.create(name="Test Business", code="TB")
        User.objects.create_user("eng", password=PASSWORD, business=biz)

    def attempt(self, password):
        return self.client.post(reverse("login"), {"username": "eng", "password": password})

    def test_five_wrong_passwords_pause_the_account(self):
        for _ in range(4):
            self.assertEqual(self.attempt("wrong").status_code, 200)
        self.assertEqual(self.attempt("wrong").status_code, 429)  # 5th failure locks
        response = self.attempt(PASSWORD)                            # even the right password
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Sign-in paused", status_code=429)

    def test_success_resets_the_counter(self):
        for _ in range(3):
            self.attempt("wrong")
        self.assertRedirects(self.attempt(PASSWORD), reverse("timetrack:dashboard"))
        self.assertFalse(AccessAttempt.objects.filter(username="eng", failures_since_start__gt=0).exists())

    def test_unlock_by_reset(self):
        for _ in range(5):
            self.attempt("wrong")
        AccessAttempt.objects.filter(username="eng").delete()  # what "unlock" in admin does
        self.assertRedirects(self.attempt(PASSWORD), reverse("timetrack:dashboard"))
