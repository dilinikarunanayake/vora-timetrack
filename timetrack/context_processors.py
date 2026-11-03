"""
Context processors add values to EVERY template automatically.
This one powers the red count badge on the "Approvals" menu item, and tells
templates whether to show money figures.
"""

from .access import timesheets_to_review
from .billing import can_see_costs


def approvals(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    ctx = {"can_see_costs": can_see_costs(user)}
    if user.can_manage_projects:
        ctx["approvals_waiting"] = timesheets_to_review(user).count()
    return ctx
