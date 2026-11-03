"""
Phase 3, step 1 of 3: create the Timesheet and TimesheetAction tables and add
a temporarily OPTIONAL timesheet link to every time entry.
(Step 2 fills the link in for existing entries; step 3 makes it required.)
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("timetrack", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Timesheet",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("week_start", models.DateField(help_text="Always a Monday.")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("SUBMITTED", "Submitted"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                        ],
                        db_index=True,
                        default="DRAFT",
                        max_length=10,
                    ),
                ),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("review_comment", models.TextField(blank=True, max_length=1000)),
                (
                    "engineer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="timesheets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-week_start", "engineer__username"],
            },
        ),
        migrations.AddField(
            model_name="timeentry",
            name="timesheet",
            field=models.ForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="entries",
                to="timetrack.timesheet",
            ),
        ),
        migrations.CreateModel(
            name="TimesheetAction",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("SUBMITTED", "Submitted"),
                            ("WITHDRAWN", "Withdrawn"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                            ("REOPENED", "Reopened"),
                        ],
                        max_length=10,
                    ),
                ),
                ("at", models.DateTimeField(auto_now_add=True)),
                ("comment", models.TextField(blank=True)),
                (
                    "by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "timesheet",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="actions",
                        to="timetrack.timesheet",
                    ),
                ),
            ],
            options={
                "ordering": ["at", "pk"],
            },
        ),
        migrations.AddConstraint(
            model_name="timesheet",
            constraint=models.UniqueConstraint(
                fields=("engineer", "week_start"),
                name="one_timesheet_per_engineer_week",
            ),
        ),
    ]
