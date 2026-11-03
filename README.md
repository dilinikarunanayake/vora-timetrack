# Vora TimeTrack

Time tracking for engineers and managers at Vora Global Solutions and Vora Nexus.

**Current stage: Phase 4.** Sign-in and roles, projects and tasks, time entries,
weekly timesheets with approval and locking, **authorised billing rates, reports and
CSV export**. All demo data and rates are fictional.

## Folder structure

```
vora_timetrack/
├── manage.py               # Command-line tool: server, migrations, tests, seed_demo
├── requirements.txt        # Python packages this project needs
├── .env.example            # Template for local secrets (copy to .env)
├── .gitignore              # Files Git must never track (.env, db, .venv)
├── config/                 # PROJECT package: settings for the whole site
│   ├── settings.py         # Apps, database, AUTH_USER_MODEL, login settings
│   └── urls.py             # Top-level routing: admin/, accounts/, app URLs
├── core/                   # APP: public landing page + form styling helper
│   └── templatetags/       # |bootstrap (form styling), |money and |hours filters
├── accounts/               # APP: businesses, users, roles, sign-in
│   ├── models.py           # Business, User (role + business)
│   ├── admin.py            # User/business screens in /admin/
│   ├── urls.py             # login, logout, change password
│   ├── migrations/         # Database change history (commit these!)
│   └── management/commands/seed_demo.py  # Loads fictional demo data
├── timetrack/              # APP: projects, tasks, time entries, timesheets, rates
│   ├── models.py           # Project, Task, Timesheet, TimesheetAction, BillingRate, TimeEntry
│   ├── billing.py          # can_see_costs(), RateBook (rate lookup), pricing at approval
│   ├── rate_views.py       # Billing rate pages (directors)
│   ├── access.py           # WHO can see WHAT (role rules, one place)
│   ├── forms.py            # Log-time, project and task forms
│   ├── views.py            # Dashboard, entry list/add/edit/delete, projects
│   ├── timesheet_views.py  # Week page, my timesheets, approvals, status actions
│   ├── context_processors.py  # Approvals count badge in the menu
│   ├── urls.py             # URL routes for the pages above
│   ├── admin.py            # Admin screens (timesheets are read-only there)
│   ├── migrations/         # 0002-0004 timesheets; 0005 billing rates
│   ├── tests.py            # Validation and access-control tests
│   └── test_timesheets.py  # Timesheet workflow and locking tests
├── reports/                # APP (no tables): reports and CSV export
│   ├── engine.py           # build_report(): filters + grouping + values, used by page AND CSV
│   ├── forms.py            # Report filters, limited to what the user may see
│   ├── views.py            # Report page, summary CSV, detailed CSV (with CSV-injection guard)
│   └── tests.py            # Rates, pricing, report scoping and CSV tests
├── templates/
│   ├── base.html           # Shared layout, navbar with user menu
│   ├── includes/form_fields.html
│   ├── registration/       # login, password change pages
│   ├── core/home.html
│   ├── timetrack/          # dashboard, entry_*, project_*, task_form,
│   │                       # timesheet_detail, my_timesheets, approvals, rate_*
│   └── reports/report.html
└── static/
    ├── css/styles.css      # Brand colours (from the logo) and layout
    └── img/                # Logo, illustrations, and image slots (see static/img/README.md)
```

## Data model

```
Business 1──< User (role: Engineer / Manager / Director)
Business 1──< Project 1──< Task 1──< TimeEntry >──1 User
                                     TimeEntry >──1 Timesheet (engineer + week) 1──< TimesheetAction
```

- Each entry is linked automatically to its engineer's **Timesheet** for that week (Monday to Sunday).

- A time entry stores the **task**. The project is reached through `task.project`.
- `TimeEntry.is_billable` is copied from the task at save time. It is billable only
  if both the project and the task are billable.
- Validation: no future dates, quarter hours only, max 24 hours per day, only open
  tasks in the engineer's own business, and dates within the project's start/end.

## Weekly timesheet workflow

```
DRAFT ──submit──> SUBMITTED ──approve──> APPROVED  (locked)
  ^                 │    └──reject──> REJECTED ──submit──> SUBMITTED
  └──withdraw───────┘
  ^
  └──reopen (director only, reason required)── APPROVED
```

- **Locked** means SUBMITTED or APPROVED: entries in that week can't be added, edited,
  moved in or out, or deleted (enforced in the model, the views and the admin).
- Rejecting needs a comment, which is shown to the engineer.
- Nobody can approve their own timesheet. Managers' timesheets go to a director.
- Every status change is recorded in `TimesheetAction` (who, when, comment).

## Billing rates and values

- A **BillingRate** is an authorised hourly price (GBP) for a business, valid between two dates.
  The most specific one wins: person-on-project, then project, then person, then business default.
- Saving a rate records **who authorised it**. Rates that have priced approved hours can't be
  re-priced or deleted, only ended. To change a price, end the old rate and add a new one.
- When a week is **approved**, each billable entry gets the rate in force on its date copied onto it
  (`TimeEntry.rate`). That price is then fixed, like an invoice line. Reopening clears it.
- Reports show **Approved value** (fixed prices) separately from **Estimated value** (today's rates
  applied to weeks not yet approved).
- Who can see money is decided by `can_see_costs()` in `timetrack/billing.py` (directors by default).

## Reports and CSV

`/reports/`: filter by date range, business, project, person and timesheet status, then group by
person, project, business, task or week. The filters live in the URL, so a report can be bookmarked.
**Summary CSV** = the table on screen; **Detailed CSV** = one row per time entry. Files open
correctly in Excel (UTF-8 with BOM), and cells starting with `= + - @` are neutralised.

## Who can do what

| | Engineer | Manager | Director |
|---|---|---|---|
| Log / edit / delete **own** time | ✅ | ✅ | – |
| See time entries | Own only | Whole business | All businesses |
| See projects | Own business | Own business | All |
| Create / edit projects & tasks | – | Own business | All |
| Submit / withdraw **own** timesheet | ✅ | ✅ | – |
| Approve / reject timesheets | – | Own business (not own) | All (not own) |
| Reopen an approved week | – | – | ✅ |
| Reports & CSV (hours) | Own time | Own business | All |
| See / set billing rates, values | – | – | ✅ |
| Django admin (`/admin/`) | – | – | Superuser only |

Records outside your scope return **404 Not Found**. Pages your role can't use
return **403 Forbidden**.

## Run it locally (macOS)

```bash
cd vora_timetrack
source .venv/bin/activate             # every new terminal
python -m pip install -r requirements.txt
python manage.py migrate              # build/update database tables
python manage.py seed_demo            # fictional demo users and data
python manage.py createsuperuser      # your own director/admin login
python manage.py test                 # 80 tests
python manage.py runserver            # http://127.0.0.1:8000/
```

`.env` must contain `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` and
`DEMO_USER_PASSWORD` (see `.env.example`).

Demo usernames: `demo.director`, `vgs.manager`, `vgs.engineer1`, `vgs.engineer2`,
`vnx.manager`, `vnx.engineer1`, `vnx.engineer2`. All use your `DEMO_USER_PASSWORD`.
`python manage.py seed_demo --reset` regenerates their entries and timesheets, with last
week in a mix of approved, submitted and rejected states. It also adds SAMPLE billing rates
(made-up round numbers) if they don't exist.

## Images and branding

- Brand colours come from the Vora Global Solutions logo: navy `#021a40`, blue `#0a6fd1`, sky `#29a8e8`.
- Illustrations in `static/img/illustrations/` are original SVGs drawn for this app.
- **Image slots:** save a file with the right name in `static/img/` (for example
  `brand/vora-nexus-logo.png` or `photos/team.jpg`) and it appears automatically.
  The full list is in `static/img/README.md`.

## Company details in the footer

Every page's footer shows the address, email, phone and copyright from `COMPANY` in
`config/settings.py`. Add the full LinkedIn and Facebook page addresses there
(`linkedin_url`, `facebook_url`) and their icons appear; leave them empty to hide them.

## Security notes

- `.env` holds secrets and is excluded from Git. Never commit it.
- Passwords are stored as one-way hashes by Django, never as plain text.
- Sign-out is a POST request with a CSRF token. Sessions end when the browser closes or after 8 hours.
- `seed_demo` refuses to run unless `DJANGO_DEBUG=True`.

## Roadmap

1. Phase 1: setup, landing page, sample dashboard ✅
2. Phase 2: models, sign-in, roles, projects/tasks, time entries ✅
3. Phase 3: weekly timesheets, submit / approve / reject, lock approved weeks ✅
4. **Phase 4: reports, CSV export, authorised billing rates and project value** ✅
5. Phase 5: PostgreSQL, production settings, online deployment
