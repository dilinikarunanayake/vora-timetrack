"""Admin site setup for projects, tasks and time entries."""

from django.contrib import admin

from .models import BillingRate, Project, Task, TimeEntry, Timesheet, TimesheetAction


class TaskInline(admin.TabularInline):
    model = Task
    extra = 1


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "business", "is_billable", "is_active"]
    list_filter = ["business", "is_billable", "is_active"]
    search_fields = ["code", "name", "client_name"]
    inlines = [TaskInline]


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ["work_date", "engineer", "task", "hours", "is_billable", "timesheet_status"]
    list_filter = ["task__project__business", "is_billable", "timesheet__status", "work_date"]
    search_fields = ["description", "engineer__username", "task__name", "task__project__name"]
    date_hierarchy = "work_date"

    actions = None  # no bulk delete: it would skip the locked-week check

    @admin.display(description="Timesheet")
    def timesheet_status(self, obj):
        return obj.timesheet.get_status_display()

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and not (obj and obj.is_locked)

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and not (obj and obj.is_locked)


class TimesheetActionInline(admin.TabularInline):
    model = TimesheetAction
    extra = 0
    can_delete = False
    readonly_fields = ["action", "by", "at", "comment"]

    def has_add_permission(self, request, obj=None):
        return False  # the audit trail is written by the app, never by hand


@admin.register(Timesheet)
class TimesheetAdmin(admin.ModelAdmin):
    """Read-only in admin: status must change through the app so it's always logged."""

    list_display = ["week_start", "engineer", "status", "submitted_at", "reviewed_by", "reviewed_at"]
    list_filter = ["status", "engineer__business", "week_start"]
    search_fields = ["engineer__username", "engineer__first_name", "engineer__last_name"]
    date_hierarchy = "week_start"
    readonly_fields = ["engineer", "week_start", "status", "submitted_at", "reviewed_by", "reviewed_at", "review_comment"]
    inlines = [TimesheetActionInline]

    def has_add_permission(self, request):
        return False


@admin.register(BillingRate)
class BillingRateAdmin(admin.ModelAdmin):
    """View-only once used: rates are managed on the Rates page so every change is authorised."""

    list_display = ["business", "project", "engineer", "hourly_rate", "effective_from", "effective_to", "authorised_by"]
    list_filter = ["business"]
    readonly_fields = ["authorised_by", "authorised_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
