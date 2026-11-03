# Putting Vora TimeTrack online

This guide takes the app from your Mac to a live, HTTPS website that your
engineers and managers can sign in to from anywhere.

**Recommended host: Render, Frankfurt (EU) region.** About **$13 a month** (≈ £10):
a $7 always-on web service plus a $6 PostgreSQL database. Check
<https://render.com/pricing> before you confirm, as prices change.

## Why Render (hosting comparison, November 2026)

| | Render (recommended) | Railway | DigitalOcean | Microsoft Azure |
|---|---|---|---|---|
| Typical monthly cost | ≈ $13 ($7 web + $6 database) | $5 minimum + usage; ≈ $5–20, varies | ≈ $20 (app + $15 database) | ≈ £25–30 (App Service B1 ≈ £11 + PostgreSQL B1ms ≈ $14 + storage) |
| Data location | EU (Frankfurt) | EU available | EU (Frankfurt/Amsterdam); London "coming soon" | **UK** (UK South, London) |
| Database backups | Point-in-time recovery, last 3 days (7 on Pro) | You manage | Daily backups + point-in-time recovery | 7–35 days, configurable |
| Setup effort | Low: this repo includes `render.yaml` | Low | Medium | Higher: more settings to manage |
| Predictable bill | Yes, fixed per service | No, usage-based | Yes | Yes |

Choose **Azure UK South** instead if your clients or contracts require data to stay
in the UK. Ask and the setup can be adapted. Hosting in the EU is generally
fine under UK data-protection law (the UK recognises the EU as "adequate"), but
mention where the data is held in your staff privacy notice. This is general
information, not legal advice.

Avoid Render's **free** tier for real use: the web service sleeps after 15
minutes, and free databases expire after 30 days with no backups.

---

## What changed in the code for production

| File | What it does |
|---|---|
| `config/settings.py` | Reads `DATABASE_URL` (PostgreSQL online, SQLite on your Mac). With `DJANGO_DEBUG=False` it forces HTTPS, secure cookies and security headers. |
| `requirements.txt` | Adds gunicorn (web server), psycopg (PostgreSQL driver), whitenoise (static files), dj-database-url, django-axes. |
| `build.sh` | Runs on each deploy: installs packages, collects static files, applies migrations. |
| `render.yaml` | Describes the live setup (database + web service, Frankfurt) so Render can create it in one step. |
| `core/views.py` → `/healthz/` | Health check that Render calls to confirm the app and database are up. |
| django-axes | After 5 wrong passwords, that username is paused for 1 hour. |

All tests pass on both SQLite and PostgreSQL 16, and `python manage.py check --deploy` reports no issues.

---

## Step 1: Update your Mac copy and check it still works

```bash
cd ~/Projects/vora_timetrack
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py test
```

`pip install` adds the new production packages. `migrate` creates the small
table django-axes uses to count failed sign-ins. You should see `OK` from the tests.

## Step 2: Put the code on GitHub (private)

Render deploys from GitHub. The repository must be **private**: it contains
your business logic, though no passwords or secrets (`.env` and the database are
excluded by `.gitignore`).

1. Create a free account at <https://github.com> if you don't have one.
2. Install the GitHub command-line tool and sign in:
   ```bash
   brew install gh
   gh auth login
   ```
   Choose **GitHub.com → HTTPS → Login with a web browser** and follow the prompts.
3. Create a private repository from your project and upload it:
   ```bash
   git status
   git branch -M main
   gh repo create vora-timetrack --private --source=. --push
   ```
   `git status` should show nothing to commit first (commit anything left over).
   `git branch -M main` names your main branch `main`. The last command creates
   the private repository and pushes your code.
4. Check on github.com that the repository exists, is marked **Private**, and that
   there is **no** `.env` or `db.sqlite3` in the file list.

## Step 3: Create the live site on Render

1. Go to <https://render.com>, choose **Get started**, and sign up **with GitHub**.
2. Add a payment card under **Billing** (the paid plans need one).
3. Click **New → Blueprint**, pick the `vora-timetrack` repository, and allow
   Render to access it.
4. Render reads `render.yaml` and lists two things to create:
   - `vora-timetrack-db`: PostgreSQL, Frankfurt, Basic 256 MB
   - `vora-timetrack`: web service, Frankfurt, Starter

   Review the monthly cost it shows, then click **Apply**. (If Render says a plan
   name isn't recognised, choose the nearest small paid plan in the form and
   continue; plan names occasionally change.)
5. Wait for the deploy to finish (5–10 minutes the first time). The log ends with
   `Your service is live`. Open the web address shown at the top, for example
   `https://vora-timetrack.onrender.com`.

Render creates `DJANGO_SECRET_KEY` and `DATABASE_URL` for you. They never appear
in your code or on your Mac.

## Step 4: Create your director account on the live site

The live database starts empty: no demo data, no users. In Render:

1. Open the **vora-timetrack** web service → **Shell** tab.
2. Run:
   ```bash
   python manage.py createsuperuser
   ```
   Enter a username, email and a **strong, new** password (not one you've used
   on your Mac). The account is automatically a Director.
3. Sign in at your live address. You'll see the empty dashboard.

## Step 5: Set up the real businesses, people and rates

Signed in as the director:

1. **Admin → Businesses → Add**: create *Vora Global Solutions* (code `VGS`) and
   *Vora Nexus* (code `VNX`).
2. **Admin → Users → Add**: for each person, set a username and a temporary
   password, then on the next screen fill in their name, email, **Role** and
   **Business**. Ask them to change the password after first sign-in (menu with
   their name → Change password).
3. **Projects**: managers (or you) add projects and tasks.
4. **Rates**: add your authorised billing rates.

## Step 6: Use your own web address (optional)

To use, for example, `timetrack.voraglobalsolutions.com`:

1. Render → web service → **Settings → Custom Domains → Add**, and enter the address.
2. At the company that manages your domain's DNS, add the **CNAME** record Render shows.
3. Render → web service → **Environment**: set `DJANGO_ALLOWED_HOSTS` to
   `timetrack.voraglobalsolutions.com` and save (the app restarts).
4. Render issues the HTTPS certificate automatically once DNS has updated (minutes to a few hours).

## Step 7: After a week of normal use

Render → web service → **Environment**: add `DJANGO_HSTS_SECONDS` = `31536000`.
This tells browsers to use HTTPS only for a year. It's left short at first so
any early mistake is easy to undo.

---

## Everyday tasks

**Deploy a change.** Commit on your Mac and push; Render redeploys automatically
and runs any new migrations:
```bash
git add -A
git commit -m "Describe the change"
git push
```

**Someone is locked out.** Admin → **Axes → Access attempts**, find the
username, select it and choose **Delete**. They can sign in straight away.

**Reset a password.** Admin → Users → the person → *this form* link under
Password.

**Backups.** Render keeps continuous point-in-time recovery for the last 3 days
(Database → **Recovery**). Once a month, also click **Create export** there and
download the file to secure company storage, so you hold a copy outside Render.
Before a big change, take an export first.

**Check it's healthy.** Render → web service → **Logs** and **Metrics**. The
health check at `/healthz/` should return `ok`.

## Security checklist

- [ ] GitHub repository is **private**; no `.env` or `db.sqlite3` in it
- [ ] Director password is new, long and not reused
- [ ] Two-factor authentication turned on for your GitHub and Render accounts
- [ ] Only directors have **Staff status / Superuser** in Admin
- [ ] Monthly database export downloaded and stored safely
- [ ] `DJANGO_HSTS_SECONDS` raised to 31536000 after the first week
