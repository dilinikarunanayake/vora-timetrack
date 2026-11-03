# Vora TimeTrack

Time tracking for engineers and managers at Vora Global Solutions and Vora Nexus.

**Current stage: Phase 1** – project skeleton, landing page and a dashboard showing
*sample* data. No login, no database tables of our own, no deployment yet.

## Folder structure

```
vora_timetrack/
├── manage.py            # Command-line tool: run server, migrations, tests
├── requirements.txt     # Python packages this project needs
├── .env.example         # Template for local secrets (copy to .env)
├── .gitignore           # Files Git must never track (.env, db, .venv)
├── config/              # PROJECT package – settings for the whole site
│   ├── settings.py      # Installed apps, database, templates, security
│   ├── urls.py          # Top-level URL routing
│   ├── wsgi.py / asgi.py# Entry points used by web servers at deployment
├── core/                # APP – landing page + dashboard
│   ├── urls.py          # URLs for this app ("/" and "/dashboard/")
│   ├── views.py         # Functions that handle each page request
│   ├── sample_data.py   # Fictional data (replaced by models in Phase 2)
│   ├── models.py        # Database tables (empty for now)
│   ├── admin.py         # Admin-site registrations (empty for now)
│   └── tests.py         # Automated tests
├── templates/
│   ├── base.html        # Shared layout: navbar, footer, Bootstrap
│   └── core/home.html, core/dashboard.html
└── static/css/styles.css# Our own styling on top of Bootstrap
```

## Run it locally (macOS)

```bash
cd vora_timetrack
python3 -m venv .venv                 # create virtual environment (once)
source .venv/bin/activate             # activate it (every new terminal)
python -m pip install -r requirements.txt
cp .env.example .env                  # then put a generated key in .env
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
python manage.py migrate              # create the SQLite database
python manage.py test                 # run the tests
python manage.py runserver            # open http://127.0.0.1:8000/
```

Stop the server with `Ctrl + C`. Leave the virtual environment with `deactivate`.

## Security notes

- `.env` holds the secret key and is excluded from Git. Never commit it.
- `DJANGO_DEBUG=True` is for your own computer only.
- All names and figures in `core/sample_data.py` are fictional. No billing rates are stored.

## Roadmap

1. **Phase 1** – setup, landing page, sample dashboard ✅
2. Phase 2 – models (Business, Project, Task, TimeEntry), login, roles
3. Phase 3 – weekly timesheets, submit / approve / reject
4. Phase 4 – reports and project cost from authorised rates
5. Phase 5 – PostgreSQL and online deployment
