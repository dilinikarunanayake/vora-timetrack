"""
Sample data for the Phase 1 dashboard.

Everything here is FICTIONAL: placeholder people, projects and tasks used
only to show how the dashboard will look. There are no billing rates.

In Phase 2 we will replace this file with real database models
(Business, Project, Task, TimeEntry, Timesheet) stored in the database.
"""

from datetime import date

BUSINESSES = ["Vora Global Solutions", "Vora Nexus"]

# Each dict is one time entry, shaped like the future TimeEntry model.
TIME_ENTRIES = [
    {"date": date(2026, 11, 2), "engineer": "Sample Engineer A", "business": "Vora Global Solutions",
     "project": "Demo Project Alpha", "task": "Site survey", "hours": 7.5, "billable": True,
     "description": "Initial survey and notes (sample)", "status": "Submitted"},
    {"date": date(2026, 11, 2), "engineer": "Sample Engineer B", "business": "Vora Global Solutions",
     "project": "Demo Project Alpha", "task": "Design review", "hours": 6.0, "billable": True,
     "description": "Reviewed draft layout (sample)", "status": "Approved"},
    {"date": date(2026, 11, 2), "engineer": "Sample Engineer C", "business": "Vora Nexus",
     "project": "Demo Project Beta", "task": "Configuration", "hours": 8.0, "billable": True,
     "description": "Configured test environment (sample)", "status": "Draft"},
    {"date": date(2026, 11, 3), "engineer": "Sample Engineer A", "business": "Vora Global Solutions",
     "project": "Internal Training", "task": "Training", "hours": 2.0, "billable": False,
     "description": "Safety refresher (sample)", "status": "Submitted"},
    {"date": date(2026, 11, 3), "engineer": "Sample Engineer B", "business": "Vora Global Solutions",
     "project": "Demo Project Gamma", "task": "Installation", "hours": 7.0, "billable": True,
     "description": "On-site installation (sample)", "status": "Rejected"},
    {"date": date(2026, 11, 3), "engineer": "Sample Engineer D", "business": "Vora Nexus",
     "project": "Demo Project Beta", "task": "Testing", "hours": 5.5, "billable": True,
     "description": "Ran acceptance tests (sample)", "status": "Submitted"},
    {"date": date(2026, 11, 3), "engineer": "Sample Engineer C", "business": "Vora Nexus",
     "project": "Internal Admin", "task": "Admin", "hours": 1.5, "billable": False,
     "description": "Weekly reporting (sample)", "status": "Draft"},
]


def dashboard_summary(entries=TIME_ENTRIES):
    """Calculate the figures shown on the dashboard from a list of entries."""
    total = sum(e["hours"] for e in entries)
    billable = sum(e["hours"] for e in entries if e["billable"])

    by_business = []
    for name in BUSINESSES:
        rows = [e for e in entries if e["business"] == name]
        hours = sum(e["hours"] for e in rows)
        by_business.append({
            "name": name,
            "hours": hours,
            "billable": sum(e["hours"] for e in rows if e["billable"]),
            "engineers": len({e["engineer"] for e in rows}),
            "share": round(hours / total * 100) if total else 0,
        })

    return {
        "total_hours": total,
        "billable_hours": billable,
        "non_billable_hours": total - billable,
        "billable_percent": round(billable / total * 100) if total else 0,
        "pending_approvals": sum(1 for e in entries if e["status"] == "Submitted"),
        "active_projects": len({e["project"] for e in entries if e["billable"]}),
        "by_business": by_business,
        "recent_entries": sorted(entries, key=lambda e: e["date"], reverse=True),
    }
