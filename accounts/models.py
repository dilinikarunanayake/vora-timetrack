"""
Accounts: businesses and users.

We use a CUSTOM USER MODEL (extending Django's built-in AbstractUser).
Django recommends this at the start of every project, because changing
the user model later is very difficult. It lets us add our own fields:
the user's role and which business they belong to.
"""

from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.db import models


class Business(models.Model):
    """A Vora company, e.g. Vora Global Solutions or Vora Nexus."""

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True, help_text="Short code, e.g. VGS")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "businesses"

    def __str__(self):
        return self.name


class VoraUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # Superusers (python manage.py createsuperuser) are always directors.
        extra_fields.setdefault("role", User.Role.DIRECTOR)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """A person who can sign in. Inherits username, password, email, names, etc."""

    class Role(models.TextChoices):
        ENGINEER = "ENGINEER", "Engineer"
        MANAGER = "MANAGER", "Manager"
        DIRECTOR = "DIRECTOR", "Director"  # sees every business

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.ENGINEER)
    business = models.ForeignKey(
        Business,
        on_delete=models.PROTECT,  # a business can't be deleted while it has users
        null=True,
        blank=True,
        related_name="users",
        help_text="Required for engineers and managers. Leave empty for directors.",
    )

    objects = VoraUserManager()

    def clean(self):
        """Model-level validation, run by forms and the admin site."""
        super().clean()
        if self.role in (self.Role.ENGINEER, self.Role.MANAGER) and not self.business_id:
            raise ValidationError({"business": "Engineers and managers must belong to a business."})

    # Convenience checks used by views and templates -------------------------

    @property
    def is_engineer(self):
        return self.role == self.Role.ENGINEER

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_director(self):
        # Superusers (created with createsuperuser) are treated as directors.
        return self.role == self.Role.DIRECTOR or self.is_superuser

    @property
    def can_manage_projects(self):
        return self.is_manager or self.is_director

    def __str__(self):
        return self.get_full_name() or self.username
