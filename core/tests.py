"""Tests for the public landing page. Run all tests with: python manage.py test"""

from django.test import TestCase, override_settings
from django.urls import reverse


class HomePageTests(TestCase):
    def test_home_page_is_public(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in")


class FooterTests(TestCase):
    def test_contact_details_on_public_and_signed_in_pages(self):
        for url in [reverse("core:home"), reverse("login")]:
            response = self.client.get(url)
            self.assertContains(response, 'href="mailto:info@voraglobalsolutions.com"')
            self.assertContains(response, 'href="tel:+447404741045"')
            self.assertContains(response, "GU14 8UT")
            self.assertContains(response, "All rights reserved.")

    def test_social_icons_hidden_until_configured(self):
        self.assertNotContains(self.client.get(reverse("core:home")), "on LinkedIn")

    @override_settings(COMPANY={"name": "Vora Global Solutions", "address": "x", "email": "a@b.c", "phone": "1",
                                "linkedin_url": "https://www.linkedin.com/company/example", "facebook_url": ""})
    def test_social_icon_shown_when_configured(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'href="https://www.linkedin.com/company/example"')
        self.assertNotContains(response, "on Facebook")
