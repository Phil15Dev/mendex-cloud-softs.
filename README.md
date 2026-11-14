# MENDEX CLOUD SOFTS · KENYA

A website and admin system that helps customers in Kenya with **government, education and everyday online services**: KRA, HELB, NTSA, KUCCPS, passport applications, TSC, SHA and more.

Customers browse the services, send a request and follow its progress with a tracking code. The owner and staff manage every request from a protected admin area.

---

## How it works

1. A customer opens the website, picks a service and sends a request with their name, phone number and details.
2. The site gives them a **tracking code** (for example `MM-A1B2C3`). They can copy it or save it on WhatsApp.
3. The business sees the new request in the admin dashboard, contacts the customer on WhatsApp and updates the status as work progresses.
4. The customer enters their code on the **Track Request** page at any time to see the status and the latest message from the business.

---

## Features

### Public website
- **Home:** hero section, "Our Services" cards, request form and contact bar
- **Services:** every service grouped as Government, Education and Online, each with its price
- **Track Request:** status, history and messages for a tracking code, with clear errors for wrong codes
- **About:** who the business is, how it works and its commitment to reliability and security
- **Contact:** WhatsApp, phone, email and a contact form that saves messages for the admin
- Responsive design for phones, tablets and desktops, with a centred navigation bar
- Phone numbers accepted as `0712 345 678`, `+254 712 345 678` or `254712345678`, saved in one format

### Admin area
- **Dashboard:** new requests today, requests waiting, in progress, completed this week, requests needing attention, a 14-day chart and the most requested services
- **Requests:** search by code, name or phone number, filter by status, open any request, change its status and add a message the customer sees
- **WhatsApp tools:** message the customer, or send them their tracking code in one click
- **Customers:** one record per phone number, with their request history
- **Services and prices:** add, edit and switch services on or off. A request keeps the price it had when it was made.
- **Reports:** summaries and CSV exports of requests and customers
- **Team:** owner, manager and staff accounts with different permissions
- **Audit log:** sign-ins and failures, status changes, price changes, exports and team changes

This version does not take or record payments.

---

## Admin security

- Passwords stored with Argon2id
- Server-side sessions in an `HttpOnly`, `SameSite=Strict` cookie, with a 30-minute idle limit and a 24-hour maximum
- CSRF protection on every admin form
- Limits on failed logins and password-reset requests
- Single-use password-reset links that expire after 15 minutes
- Roles with permissions, and re-entering the password before sensitive changes
- Security headers, including a strict Content-Security-Policy, with no inline scripts or styles

| Permission | Owner | Manager | Staff |
|---|:-:|:-:|:-:|
| View and update requests, customers and reports | ✓ | ✓ | ✓ |
| Manage services and prices, export CSV | ✓ | ✓ | |
| Manage the team, view the audit log | ✓ | | |

---

## Built with

| Part | Technology |
|---|---|
| Backend | Python, FastAPI |
| Pages | Jinja2 templates, Tailwind CSS, a little plain JavaScript |
| Database | PostgreSQL (SQLite for local trials), SQLAlchemy 2, Alembic migrations |
| Rate limits | Redis (optional) |
| Tests | pytest: unit, integration and security tests |
| Deployment | Docker |

---

## Project layout

```text
app/
  main.py            app setup, middleware, error pages, health checks
  core/              configuration, database, security, logging, helpers
  modules/
    auth/            admin accounts, sessions, sign-in, password reset
    admin/           roles, permissions, audit log, team pages
    services/        services and categories
    customers/       customers
    requests/        requests, status history, public pages, tracking
    reports/         dashboard, reports, CSV exports
    notifications/   alerts and email
  templates/         public, auth and admin pages
  static/            styles, scripts and logo
migrations/          database migrations
tests/               unit, integration and security tests
```

---

## Getting started

You need Python 3.11 or newer.

```bash
git clone https://github.com/phil15Dev/mendex-cloud-softs.git
cd mendex-cloud-softs
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and fill in the values. `.env.example` explains each one, and the `.env` file must never be committed.

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

The site runs at http://localhost:8000 and the admin at http://localhost:8000/admin/login.

Run the tests with:

```bash
pip install -r requirements-dev.txt
pytest -q
```

---

## Status

Tested with an automated test suite. Online payments are not part of this version.

## Contact

MENDEX CLOUD SOFTS · KENYA
WhatsApp and phone: +254 708 337 199
Email: mendexbackup072@gmail.com
