"""Admin site setup for businesses and users (director use only)."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Business, User


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "is_active"]


@admin.register(User)
class VoraUserAdmin(UserAdmin):
    # Add our two fields to Django's standard user screens.
    fieldsets = UserAdmin.fieldsets + (("Vora", {"fields": ("role", "business")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Vora", {"fields": ("first_name", "last_name", "email", "role", "business")}),
    )
    list_display = ["username", "first_name", "last_name", "role", "business", "is_active"]
    list_filter = ["role", "business", "is_active"]
