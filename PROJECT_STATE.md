# PROJECT_STATE

Last updated: 2026-11-11. Architecture: modular monolith (FastAPI, Jinja2, Tailwind, PostgreSQL, SQLAlchemy 2, Alembic, Redis, server-side sessions).

## Done (94 automated tests passed on SQLite and on PostgreSQL 16 + Redis before payments were removed; the suite has not been re-run since, see Not done / not verified)
- Phase 1-2  Core: settings with production safety check, database layer, JSON logging with request ids, error pages, health checks.
- Phase 3    Database models by module; one Alembic migration (16 tables); foreign keys protect request history.
- Phase 4    Authentication: Argon2id, hashed server-side sessions, idle/absolute expiry, fixation protection, Redis throttling with fallback, forgot/reset (15 min, single use, revokes sessions), password change, CLI recovery, CSRF tokens, re-authentication for sensitive actions, security headers and CSP.
- Phase 5    RBAC (owner, manager, staff from 8 permissions), team management, audit log and page.
- Phase 6-7  Services with categories (admin add/edit/hide, never deleted), customers (one per phone), requests with status history, public site, tracking page with timeline, JSON API.
- Phase 8    Removed on 2026-11-11: payments (recording, reversal, payment status, payments page and CSV, collected-money figures). The fee-when-requested snapshot on each request stays.
- Phase 9    Dashboard (cards, 14-day chart, top services, needs attention), reports by date, CSV exports (requests, customers; BOM, formula-safe, permission-checked, audited), in-app notifications.
- Phase 10   Email log, SMTP sending in a background task, optional new-request email to `NOTIFY_ADMIN_EMAIL`.

## Decisions
- Confirmed on 2026-11-11: the admin login stays on server-side sessions. JWT access tokens with rotating refresh tokens were considered and not adopted.
- Server-side sessions instead of JWT: revocable immediately; fits a browser-only admin. Add token auth later only if a mobile app or third-party client appears.
- CSRF token = HMAC(secret, session token): nothing extra to store; different per session.
- Prices are snapshotted per request. Payments were removed from this version on purpose.
- Alembic owns the schema. The app checks at startup and refuses to run on an unmigrated database.

## Not done / not verified
- After removing payments on 2026-11-11 the code compiles and every template parses, but the test suite, the Alembic migration and the running app were NOT run (the packages could not be installed). Run `alembic upgrade head` on a new database, then `pytest`, before relying on this. An existing database made from the old migration must be recreated.
- Docker files (`Dockerfile`, `docker-compose.yml`) were written but not run in this environment.
- Real SMTP delivery was not tested (the logged path and the log table are).
- Not clicked through in a real browser or on a phone; pages were tested through HTTP responses, headers and a live server with curl.
- No payment tracking and no M-Pesa integration. Add them back only if the client asks.
- Background email uses FastAPI background tasks (lost if the process dies mid-send). A durable queue (Redis + a worker) is the next step if email becomes important.
- No customer SMS/WhatsApp notifications, no error monitoring service (for example Sentry), no automated dependency updates.
- No load test has been run; lists are paginated and indexed.

## Next
Frontend work, customer notifications, error monitoring, load test, restore drill.
