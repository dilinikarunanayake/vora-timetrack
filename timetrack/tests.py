"""
Tests for models, validation and role-based access.

Run with:  python manage.py test
Each test gets a fresh, empty test database, so nothing touches your real data.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Business, User
from timetrack.models import Project, Task, TimeEntry

PASSWORD = "test-only-password-123"


class BaseSetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vgs = Business.objects.create(name="Test Business A", code="TBA")
        cls.vnx = Business.objects.create(name="Test Business B", code="TBB")

        def make_user(username, role, business):
            return User.objects.create_user(username, password=PASSWORD, role=role, business=business)

        cls.eng_a = make_user("eng_a", User.Role.ENGINEER, cls.vgs)
        cls.eng_a2 = make_user("eng_a2", User.Role.ENGINEER, cls.vgs)
        cls.mgr_a = make_user("mgr_a", User.Role.MANAGER, cls.vgs)
        cls.eng_b = make_user("eng_b", User.Role.ENGINEER, cls.vnx)
        cls.director = make_user("director", User.Role.DIRECTOR, None)

        cls.proj_a = Project.objects.create(business=cls.vgs, code="A-1", name="Project A")
        cls.task_a = Task.objects.create(project=cls.proj_a, name="Build")
        cls.internal_a = Project.objects.create(business=cls.vgs, code="A-INT", name="Internal", is_billable=False)
        cls.task_internal = Task.objects.create(project=cls.internal_a, name="Training")
        cls.proj_b = Project.objects.create(business=cls.vnx, code="B-1", name="Project B")
        cls.task_b = Task.objects.create(project=cls.proj_b, name="Test")

        cls.today = timezone.localdate()
        cls.entry_a = TimeEntry.objects.create(engineer=cls.eng_a, work_date=cls.today, task=cls.task_a,
                                               hours=Decimal("6"), description="A's work")
        cls.entry_a2 = TimeEntry.objects.create(engineer=cls.eng_a2, work_date=cls.today, task=cls.task_a,
                                                hours=Decimal("4"), description="A2's work")
        cls.entry_b = TimeEntry.objects.create(engineer=cls.eng_b, work_date=cls.today, task=cls.task_b,
                                               hours=Decimal("5"), description="B's work")

    def login(self, user):
        self.client.force_login(user)


class ModelValidationTests(BaseSetup):
    def entry(self, **kwargs):
        data = {"engineer": self.eng_a, "work_date": self.today, "task": self.task_a,
                "hours": Decimal("1"), "description": "x"}
        data.update(kwargs)
        return TimeEntry(**data)

    def test_billable_copied_from_project_and_task(self):
        self.assertTrue(self.entry_a.is_billable)
        e = self.entry(task=self.task_internal)
        e.save()
        self.assertFalse(e.is_billable)

    def test_future_date_rejected(self):
        with self.assertRaises(ValidationError):
            self.entry(work_date=self.today + timedelta(days=1)).full_clean()

    def test_quarter_hours_only(self):
        with self.assertRaises(ValidationError):
            self.entry(hours=Decimal("1.1")).full_clean()
        self.entry(hours=Decimal("1.75")).full_clean()  # fine

    def test_other_business_project_rejected(self):
        with self.assertRaises(ValidationError):
            self.entry(task=self.task_b).full_clean()

    def test_more_than_24_hours_a_day_rejected(self):
        with self.assertRaises(ValidationError):
            self.entry(hours=Decimal("18.25")).full_clean()  # already 6h logged

    def test_closed_task_rejected(self):
        closed = Task.objects.create(project=self.proj_a, name="Closed", is_active=False)
        with self.assertRaises(ValidationError):
            self.entry(task=closed).full_clean()

    def test_superuser_is_director(self):
        admin = User.objects.create_superuser("boss", password=PASSWORD)
        self.assertEqual(admin.role, User.Role.DIRECTOR)
        self.assertTrue(admin.is_director)

    def test_engineer_must_have_business(self):
        with self.assertRaises(ValidationError):
            User(username="nobiz", role=User.Role.ENGINEER).full_clean()


class LoginTests(BaseSetup):
    def test_pages_require_login(self):
        for name in ["timetrack:dashboard", "timetrack:entry_list", "timetrack:project_list"]:
            response = self.client.get(reverse(name))
            self.assertRedirects(response, f"{reverse('login')}?next={reverse(name)}")

    def test_login_with_correct_password(self):
        response = self.client.post(reverse("login"), {"username": "eng_a", "password": PASSWORD})
        self.assertRedirects(response, reverse("timetrack:dashboard"))

    def test_login_with_wrong_password(self):
        response = self.client.post(reverse("login"), {"username": "eng_a", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "match. Please try again")

    def test_logout_requires_post(self):
        self.login(self.eng_a)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("core:home"))


class EngineerAccessTests(BaseSetup):
    def setUp(self):
        self.login(self.eng_a)

    def test_sees_only_own_entries(self):
        response = self.client.get(reverse("timetrack:entry_list"))
        self.assertContains(response, "A&#x27;s work")
        self.assertNotContains(response, "A2&#x27;s work")
        self.assertNotContains(response, "B&#x27;s work")

    def test_can_log_time(self):
        response = self.client.post(reverse("timetrack:entry_add"), {
            "work_date": self.today.isoformat(), "task": self.task_a.pk, "hours": "1.5", "description": "New",
        })
        self.assertRedirects(response, reverse("timetrack:entry_list"))
        self.assertTrue(TimeEntry.objects.filter(engineer=self.eng_a, description="New").exists())

    def test_cannot_pick_other_business_task(self):
        response = self.client.post(reverse("timetrack:entry_add"), {
            "work_date": self.today.isoformat(), "task": self.task_b.pk, "hours": "1", "description": "Sneaky",
        })
        self.assertEqual(response.status_code, 200)  # form shown again with an error
        self.assertFalse(TimeEntry.objects.filter(description="Sneaky").exists())

    def test_cannot_edit_or_delete_colleagues_entry(self):
        self.assertEqual(self.client.get(reverse("timetrack:entry_edit", args=[self.entry_a2.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("timetrack:entry_delete", args=[self.entry_a2.pk])).status_code, 404)
        self.assertTrue(TimeEntry.objects.filter(pk=self.entry_a2.pk).exists())

    def test_can_delete_own_entry(self):
        self.client.post(reverse("timetrack:entry_delete", args=[self.entry_a.pk]))
        self.assertFalse(TimeEntry.objects.filter(pk=self.entry_a.pk).exists())

    def test_cannot_manage_projects(self):
        self.assertEqual(self.client.get(reverse("timetrack:project_add")).status_code, 403)

    def test_cannot_see_other_business_project(self):
        self.assertEqual(self.client.get(reverse("timetrack:project_detail", args=[self.proj_b.pk])).status_code, 404)


class ManagerAccessTests(BaseSetup):
    def setUp(self):
        self.login(self.mgr_a)

    def test_sees_whole_business_but_not_other_business(self):
        response = self.client.get(reverse("timetrack:entry_list"))
        self.assertContains(response, "A&#x27;s work")
        self.assertContains(response, "A2&#x27;s work")
        self.assertNotContains(response, "B&#x27;s work")

    def test_cannot_edit_engineers_entry(self):
        self.assertEqual(self.client.get(reverse("timetrack:entry_edit", args=[self.entry_a.pk])).status_code, 404)

    def test_creates_project_in_own_business(self):
        self.client.post(reverse("timetrack:project_add"), {"code": "a-2", "name": "New", "is_billable": "on", "is_active": "on"})
        project = Project.objects.get(code="A-2")
        self.assertEqual(project.business, self.vgs)

    def test_duplicate_project_code_rejected(self):
        response = self.client.post(reverse("timetrack:project_add"), {"code": "A-1", "name": "Dup"})
        self.assertContains(response, "already exists")

    def test_cannot_add_task_to_other_business_project(self):
        url = reverse("timetrack:task_add", args=[self.proj_b.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_adds_task(self):
        self.client.post(reverse("timetrack:task_add", args=[self.proj_a.pk]), {"name": "Survey", "is_billable": "on", "is_active": "on"})
        self.assertTrue(Task.objects.filter(project=self.proj_a, name="Survey").exists())


class DirectorAccessTests(BaseSetup):
    def test_sees_everything(self):
        self.login(self.director)
        response = self.client.get(reverse("timetrack:entry_list"))
        for text in ["A&#x27;s work", "A2&#x27;s work", "B&#x27;s work"]:
            self.assertContains(response, text)
        dashboard = self.client.get(reverse("timetrack:dashboard"))
        self.assertContains(dashboard, "Hours by business")

    def test_director_cannot_log_time(self):
        self.login(self.director)
        self.assertEqual(self.client.get(reverse("timetrack:entry_add")).status_code, 403)
