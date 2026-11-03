"""
Role-based access rules, kept in ONE place.

Every view gets its data through these functions, so a user can never see
records outside their scope, even by typing an ID into the address bar
(they get a 404 "not found" instead).

    Director  -> everything, across both businesses
    Manager   -> everything in their own business
    Engineer  -> their own time entries; their business's projects (read-only)

Timesheets follow the same pattern. Reviewing has one extra rule, in
Timesheet.can_review(): nobody can approve their own timesheet.
"""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from .models import Project, Task, TimeEntry, Timesheet


def visible_projects(user):
    qs = Project.objects.select_related("business")
    if user.is_director:
        return qs
    return qs.filter(business_id=user.business_id)


def visible_tasks(user):
    return Task.objects.select_related("project__business").filter(project__in=visible_projects(user))


def visible_entries(user):
    qs = TimeEntry.objects.select_related("engineer", "task__project__business")
    if user.is_director:
        return qs
    if user.is_manager:
        return qs.filter(engineer__business_id=user.business_id)
    return qs.filter(engineer=user)


def visible_timesheets(user):
    qs = Timesheet.objects.select_related("engineer__business", "reviewed_by")
    if user.is_director:
        return qs
    if user.is_manager:
        return qs.filter(engineer__business_id=user.business_id)
    return qs.filter(engineer=user)


def timesheets_to_review(user):
    """Submitted timesheets this user may approve (never their own)."""
    if not user.can_manage_projects:
        return Timesheet.objects.none()
    return visible_timesheets(user).filter(status=Timesheet.Status.SUBMITTED).exclude(engineer=user)


def can_log_time(user):
    """Engineers and managers record their own time; directors don't belong to one business."""
    return user.is_authenticated and user.business_id is not None


class ManagerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow managers and directors only. Others get 403 Forbidden."""

    def test_func(self):
        return self.request.user.can_manage_projects


class CanLogTimeMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return can_log_time(self.request.user)
