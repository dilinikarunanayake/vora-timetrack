"""
Phase 3, step 3 of 3: every time entry now has a timesheet, so make the link
required. From here on, TimeEntry.save() always sets it.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("timetrack", "0003_link_entries_to_timesheets")]

    operations = [
        migrations.AlterField(
            model_name="timeentry",
            name="timesheet",
            field=models.ForeignKey(
                editable=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="entries",
                to="timetrack.timesheet",
            ),
        ),
    ]
