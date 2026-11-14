# mendex-cloud-softs.
# MENDEX CLOUD SOFTS · KENYA

Website and admin system for **MENDEX CLOUD SOFTS · KENYA**, a business that helps customers with government, education and everyday online services (KRA, HELB, NTSA, KUCCPS, passports, TSC, SHA and more).

Customers browse the services, send a request and follow its progress with a tracking code. The owner and staff manage everything from a protected admin area.

**Stack:** FastAPI · Jinja2 · Tailwind CSS · SQLAlchemy 2 · Alembic · PostgreSQL (SQLite for local use) · Redis (optional). One application serves the public site, the tracking page, a small JSON API and the admin dashboard.

---

## What is in it

**Public website**
- Home, Services, Track Request, About and Contact pages, with a navbar that stays centred on every screen size
- Services grouped as Government, Education and Online, each with its price
- Get Started request form and a Contact form that saves messages for the admin
- Tracking page: the customer enters a code such as `MM-A1B2C3` and sees the status and updates
- After sending a request the customer can **Copy code** or **Save code on WhatsApp**
- WhatsApp and phone buttons, and a "Need help?" bar with the business contact details

**Admin area** (`/admin/login`)
- Dashboard, requests, customers, services and prices, reports, team and audit log
- Change a request's status and add a message the customer sees on the tracking page
- **Send tracking code on WhatsApp** button on each request
- Search by request code, customer name or phone number, typed as `07...` or `+254...`
- CSV exports for requests and customers
- Roles: owner, manager and staff

**Phone numbers** are accepted as `0712 345 678`, `+254 712 345 678`, `254712345678` or `712345678`, and are saved in one format so a customer never appears twice.

This version does **not** record or take payments. A request keeps the service price as it was when the request was made.

---

## Run it on your computer

You need Python 3.11 or newer.

```bash
git clone https://github.com/phil15Dev/mendex-cloud-softs.git
cd mendex-cloud-softs

python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                 # Windows: copy .env.example .env
```

Open `.env` and make at least these changes (no Docker or PostgreSQL is needed for a local trial):

```dotenv
DATABASE_URL=sqlite:///./iammendexmendle.db
REDIS_URL=
SECRET_KEY=<a long random value, see below>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<your own long password>
```

Create a secret key with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Then create the tables and start the site:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

- Website: http://localhost:8000
- Admin: http://localhost:8000/admin/login
- The first administrator (role: owner) is created from `ADMIN_USERNAME` and `ADMIN_PASSWORD` the first time the app starts.
- The app refuses to start until `alembic upgrade head` has been run. It never changes tables by itself.

To use PostgreSQL and Redis instead, run `docker compose up -d db redis` and keep the PostgreSQL `DATABASE_URL` and `REDIS_URL` lines from `.env.example`.

---

## Settings (`.env`)

`.env.example` explains every value. The important ones:

| Setting | What it does |
|---|---|
| `APP_ENV` | `development` or `production`. Production refuses weak secrets and passwords. |
| `DATABASE_URL` | PostgreSQL (recommended) or SQLite for local trials. |
| `REDIS_URL` | Shared rate limits. Leave empty to use per-process limits. |
| `SECRET_KEY` | Long random value. Keep it private. Changing it signs everyone out. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_EMAIL` | The first owner account. The email can also be used to sign in. |
| `HTTPS_ONLY` | `true` on the live site (secure cookies). |
| `BUSINESS_NAME`, `WHATSAPP_NUMBER`, `CONTACT_EMAIL`, `WHATSAPP_CHANNEL_URL` | Shown on the website. |
| `PUBLIC_BASE_URL` | The real website address. Tracking links in WhatsApp messages and emails use it. |
| `SMTP_*`, `NOTIFY_ADMIN_EMAIL` | Optional email sending. Without them, reset links and emails are written to the log in development. |

**Never commit `.env`.** It is already listed in `.gitignore`.

For Gmail, set `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, your address as `SMTP_USER` and `SMTP_FROM`, and a Google **app password** (not your normal password) as `SMTP_PASSWORD`.

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Tests use an in-memory SQLite database and never touch your `.env` database. To run them against the real stack:

```bash
TEST_DATABASE_URL=postgresql+psycopg://imm:imm_dev_pw@localhost:5432/iammendexmendle_test \
TEST_REDIS_URL=redis://localhost:6379/0 pytest
```

Tests always build the schema from the Alembic migrations, and one test fails if the models and migrations disagree.

---

## Deploying

The project includes a `Dockerfile`. On start it runs `alembic upgrade head` and then serves the site, so the database is prepared on every deploy.

Production checklist:
1. `APP_ENV=production`, a new `SECRET_KEY` of 32+ characters, a strong `ADMIN_PASSWORD` and `HTTPS_ONLY=true`.
2. Use PostgreSQL. A SQLite file is fine locally but is lost on hosts without permanent disk space.
3. Set `PUBLIC_BASE_URL` to the real address, for example `https://yourdomain.co.ke`.
4. Serve over HTTPS (the hosting platform, Caddy or Nginx). Start with `uvicorn app.main:app --workers 2 --proxy-headers` if you do not use the Dockerfile.
5. Add Redis (`REDIS_URL`) when you run more than one process, so login limits are shared.
6. Back up PostgreSQL daily (`scripts/backup_postgres.sh`) and test a restore.
7. Watch the JSON logs (each request has an `X-Request-ID`) and `/health/ready`.

Locked out and no email set up? Run `python -m app.cli reset-password [username]` on the server. It sets a new password and signs everything out.

---

## Admin security in short

| Area | What is built |
|---|---|
| Passwords | Argon2id. A wrong username and a wrong password give the same message. |
| Sessions | Server-side sessions, not JWT. A random token in an `HttpOnly`, `SameSite=Strict` cookie limited to `/admin`, with only its SHA-256 hash stored. 30 minutes idle, 24 hours at most. Logout revokes it in the database. |
| CSRF | Every admin form carries a token; posts from other sites are blocked. |
| Throttling | Failed logins and reset requests are limited per IP and username (Redis, with an in-memory fallback). |
| Password reset | Single-use link valid for 15 minutes. A reset or password change signs out every session. |
| Re-authentication | Creating or changing administrators, and changing your own password, ask for the password again. |
| Roles | `owner`, `manager`, `staff`. The last active owner cannot be removed. |
| Audit log | Sign-ins and failures, status changes, price changes, exports and team changes. |
| Headers | Content-Security-Policy without inline scripts or styles, `X-Frame-Options: DENY`, `nosniff`, no-store and noindex on admin pages, HSTS when `HTTPS_ONLY=true`. |

| Permission | owner | manager | staff |
|---|:-:|:-:|:-:|
| View and update requests, view customers and reports | yes | yes | yes |
| Manage services and prices, export CSV | yes | yes | no |
| Manage administrators, view the audit log | yes | no | no |

---

## Project layout

```
app/
  main.py            app, middleware, error pages, health checks
  core/              config, database, security, rate limits, logging, templating, helpers
  modules/
    auth/            admins, sessions, password reset, login routes
    admin/           roles, permissions, audit log, team pages
    services/        services and categories
    customers/       customers (one per phone number)
    requests/        requests, status history, public site, tracking page, public API
    reports/         dashboard, reports, CSV exports
    notifications/   in-app alerts, email log, SMTP sending
  templates/         public/  auth/  admin/  errors/
  static/            tailwind.css, site.css, auth.css, app.js, logo
migrations/          Alembic migrations
tests/               unit/  integration/  security/
```

## Changing the design

Page styles are in `app/static/site.css` (public pages) and `app/static/auth.css` (login pages). Tailwind classes are in `app/templates`. After changing Tailwind classes run `npm install && npm run build:css`. The compiled CSS is committed, so Node is not needed to run the site.

A hero photo can be added as `app/static/hero.jpg`; the site uses it automatically in place of the drawn illustration.

---

Project history and decisions are in `PROJECT_STATE.md`.
