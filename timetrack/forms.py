"""
Forms turn HTML form input into validated Python data.

A ModelForm builds its fields from a model, then runs the model's own
validation (the clean() methods in models.py) before saving.
"""

from django import forms
from django.utils import timezone

from accounts.models import User

from .access import visible_projects
from .models import BillingRate, Project, Task, TimeEntry


class DateInput(forms.DateInput):
    """Browser date picker. HTML date inputs always need the value as YYYY-MM-DD."""

    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%Y-%m-%d")


class TaskChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, task):
        flag = "" if task.billable else "  (non-billable)"
        return f"{task.project.code} {task.project.name} › {task.name}{flag}"


class TimeEntryForm(forms.ModelForm):
    task = TaskChoiceField(queryset=Task.objects.none(), label="Project › Task")

    class Meta:
        model = TimeEntry
        fields = ["work_date", "task", "hours", "description"]
        widgets = {
            "work_date": DateInput(),
            "hours": forms.NumberInput(attrs={"step": "0.25", "min": "0.25", "max": "24"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"work_date": "Work date", "description": "Work description"}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        # The engineer is always the signed-in user, never chosen in the form.
        self.instance.engineer = user
        # Only active tasks on active projects in the user's own business.
        tasks = Task.objects.select_related("project").filter(
            project__business_id=user.business_id, is_active=True, project__is_active=True
        )
        if self.instance.pk:  # editing: keep the current task selectable
            tasks = tasks | Task.objects.filter(pk=self.instance.task_id)
        self.fields["task"].queryset = tasks.order_by("project__code", "name").distinct()
        if not self.instance.pk and not self.initial.get("work_date"):
            self.initial["work_date"] = timezone.localdate()


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["business", "code", "name", "client_name", "is_billable", "is_active", "start_date", "end_date"]
        widgets = {"start_date": DateInput(), "end_date": DateInput()}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if not user.is_director:
            # Managers can only create projects in their own business.
            del self.fields["business"]
            self.instance.business_id = user.business_id

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        business_id = self.cleaned_data.get("business", None)
        business_id = business_id.pk if business_id else self.instance.business_id
        clash = Project.objects.filter(business_id=business_id, code=code).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("A project with this code already exists in this business.")
        return code


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["name", "is_billable", "is_active"]

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.project = project

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = Task.objects.filter(project=self.instance.project, name__iexact=name).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("This project already has a task with that name.")
        return name


class EntryFilterForm(forms.Form):
    """Filters on the time entry list (all optional)."""

    start = forms.DateField(required=False, widget=DateInput(), label="From")
    end = forms.DateField(required=False, widget=DateInput(), label="To")
    project = forms.ModelChoiceField(queryset=Project.objects.none(), required=False, empty_label="All projects")

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = visible_projects(user)


class BillingRateForm(forms.ModelForm):
    """Add or edit a rate. Once a rate has priced approved hours, only its
    end date and notes can change (the price itself is part of the record)."""

    class Meta:
        model = BillingRate
        fields = ["business", "project", "engineer", "hourly_rate", "effective_from", "effective_to", "notes"]
        widgets = {"effective_from": DateInput(), "effective_to": DateInput()}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        # Whoever saves the rate is recorded as authorising it.
        self.instance.authorised_by = user
        self.fields["project"].queryset = Project.objects.select_related("business").order_by("business__code", "code")
        self.fields["project"].label_from_instance = lambda p: f"{p.business.code} · {p.code} {p.name}"
        self.fields["engineer"].queryset = (
            User.objects.filter(business__isnull=False).select_related("business").order_by("business__code", "first_name")
        )
        self.fields["engineer"].label_from_instance = lambda u: f"{u.business.code} · {u} ({u.get_role_display()})"
        self.fields["project"].empty_label = "All projects in the business"
        self.fields["engineer"].empty_label = "Everyone"
        if self.instance.is_used:
            for name in ["business", "project", "engineer", "hourly_rate", "effective_from"]:
                self.fields[name].disabled = True  # shown, but can't be changed
