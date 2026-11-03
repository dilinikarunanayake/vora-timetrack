"""
Phase 3, step 2 of 3 (a DATA migration): give every existing time entry a
weekly timesheet. Creates one DRAFT timesheet per engineer per week that
already has entries, and links the entries to it.
"""

from datetime import timedelta

from django.db import migrations


def link_existing_entries(apps, schema_editor):
    # Use the "historical" models from `apps`, never a direct import: they match
    # the database exactly as it is at this point in the migration history.
    Timesheet = apps.get_model("timetrack", "Timesheet")
    TimeEntry = apps.get_model("timetrack", "TimeEntry")
    for entry in TimeEntry.objects.filter(timesheet__isnull=True).iterator():
        monday = entry.work_date - timedelta(days=entry.work_date.weekday())
        sheet, _ = Timesheet.objects.get_or_create(engineer_id=entry.engineer_id, week_start=monday)
        entry.timesheet_id = sheet.pk
        entry.save(update_fields=["timesheet"])


def unlink_entries(apps, schema_editor):
    """Reverse step (used if you ever migrate back to 0001): nothing to undo."""


class Migration(migrations.Migration):

    dependencies = [("timetrack", "0002_timesheets")]

    operations = [migrations.RunPython(link_existing_entries, unlink_entries)]
