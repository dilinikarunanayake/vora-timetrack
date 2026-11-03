"""The report filter form. Choices are limited to what the user is allowed to see."""

from datetime import timedelta

from django import forms
from django.utils import timezone

from accounts.models import Business, User
from timetrack.access import visible_projects
from timetrack.forms import DateInput

from .engine import GROUPINGS, STATUS_FILTERS

MAX_RANGE_DAYS = 731  # two years per report keeps pages fast


def default_filters():
    today = timezone.localdate()
    return {"start": today.replace(day=1), "end": today, "group_by": "engineer", "status": "approved"}


class ReportForm(forms.Form):
    start = forms.DateField(widget=DateInput(), label="From")
    end = forms.DateField(widget=DateInput(), label="To")
    group_by = forms.ChoiceField(choices=list(GROUPINGS.items()), label="Group by")
    status = forms.ChoiceField(choices=[(k, v[0]) for k, v in STATUS_FILTERS.items()], label="Timesheets")
    business = forms.ModelChoiceField(queryset=Business.objects.all(), required=False, empty_label="All businesses")
    project = forms.ModelChoiceField(queryset=None, required=False, empty_label="All projects")
    engineer = forms.ModelChoiceField(queryset=None, required=False, empty_label="Everyone", label="Person")

    def __init__(self, data, *, user, **kwargs):
        # Fill in defaults for anything not in the address bar, so the page
        # always shows a report (this month, by engineer, approved only).
        merged = {k: v for k, v in default_filters().items()}
        merged.update({k: v for k, v in data.items() if v != "" or k in ("business", "project", "engineer")})
        super().__init__(merged, **kwargs)

        self.fields["project"].queryset = visible_projects(user).order_by("business__code", "code")
        self.fields["project"].label_from_instance = lambda p: f"{p.code} · {p.name}"
        people = User.objects.filter(business__isnull=False).select_related("business")
        if not user.is_director:
            del self.fields["business"]
            people = people.filter(business_id=user.business_id)
        if user.is_engineer:
            del self.fields["engineer"]  # engineers only ever see their own time
        else:
            self.fields["engineer"].queryset = people.order_by("business__code", "first_name")
            self.fields["engineer"].label_from_instance = lambda u: (
                f"{u} ({u.business.code})" if user.is_director else str(u)
            )

    def clean(self):
        data = super().clean()
        start, end = data.get("start"), data.get("end")
        if start and end:
            if end < start:
                raise forms.ValidationError("'To' must be on or after 'From'.")
            if (end - start) > timedelta(days=MAX_RANGE_DAYS):
                raise forms.ValidationError("Please choose a range of two years or less.")
        return data
