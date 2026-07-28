# Booking System API

[![CI](https://github.com/alpondr/booking-system-api/actions/workflows/ci.yml/badge.svg)](https://github.com/alpondr/booking-system-api/actions/workflows/ci.yml)

A simple appointment booking API built with FastAPI + PostgreSQL, made as a
learning project. Users can register, browse services, and book
appointments. There's overlap checking so two appointments can't be booked
for the same time slot.

Live: https://booking-system-api-0stg.onrender.com/docs

Free tier, so the first request after an idle period is slow while Render
and Neon wake up.

## Tech stack

- Python 3.13 (pinned in `.python-version`)
- FastAPI
- PostgreSQL + SQLAlchemy
- Alembic (migrations)
- Pydantic (validation)
- JWT auth (python-jose + passlib)
- Docker Compose (for the database)
- pytest (tests) + GitHub Actions (CI)
- Deployed on Render, database on Neon

## Project structure

```
app/
  core/        config, JWT/password helpers, auth dependencies
  database/    engine, session, declarative base
  models/      SQLAlchemy models (User, Service, Appointment)
  schemas/     Pydantic request/response models
  services/    business logic (overlap checking, slot calculation, etc.)
  routers/     FastAPI endpoints
alembic/       DB migrations
tests/         pytest suite, fixtures in conftest.py
```

Business logic (like the overlap check) lives in `app/services/`, not in
the routers. Routers just handle HTTP stuff and call into that layer.

## Setup

1. Clone the repo and create a virtualenv:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Copy the env file and fill in your own values:

```bash
cp .env.example .env
```

At minimum set a real `SECRET_KEY` (e.g. `python3 -c "import secrets; print(secrets.token_hex(32))"`)
and make sure `DATABASE_URL` matches the `POSTGRES_*` values.

3. Start PostgreSQL:

```bash
docker compose up -d
```

4. Run migrations:

```bash
alembic upgrade head
```

5. Run the API:

```bash
uvicorn app.main:app --reload
```

Docs available at `http://localhost:8000/docs`.

## Running tests

Tests use a separate database - they drop and recreate every table. Create
it once and set `TEST_DATABASE_URL` in `.env` (see `.env.example`):

```bash
docker compose exec db createdb -U booking_user booking_test
pip install -r requirements-dev.txt
pytest
```

Coverage report: `pytest --cov=app --cov-report=term-missing`.

The same suite runs on GitHub Actions for every push and pull request.

## Deployment

Render web service + Neon Postgres.

- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Env vars on Render: `DATABASE_URL` (Neon's pooled string), `SECRET_KEY`,
  `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`

Migrations are run locally before deploying, against Neon's direct
(non-pooled) string:

```bash
DATABASE_URL="<neon-direct-url>" alembic upgrade head
```

## Notes on some design decisions

- **Timestamps are stored in UTC** (`TIMESTAMPTZ` columns), and the API only
  accepts timezone-aware datetimes for `start_time`. Working hours
  (09:00-18:00) are checked against `Europe/Istanbul` local time though,
  since "working hours" is a local, not UTC, concept.
- **Cancelling an appointment is a soft delete** - the row stays, only
  `status` changes to `cancelled`. Nothing gets deleted from the DB.
- **Overlap checking** only looks at `ACTIVE` appointments, so a cancelled
  slot frees up immediately.
- **Tests run on Postgres, not SQLite.** SQLite has no timezone type and
  returns naive datetimes for the `TIMESTAMPTZ` columns the overlap logic
  depends on, so it would test different behaviour than production.
- **Each test is rolled back**, using a session bound with
  `join_transaction_mode="create_savepoint"` so the app's own `db.commit()`
  calls can be undone too.
- There's no per-resource/per-staff booking here - it's modeled as a
  single-provider business (one appointment at a time, regardless of
  which service). Adjust `has_overlap` in
  `app/services/appointment_service.py` if you need multiple resources.

## Roles

New users always register with the `user` role - there's no way to
self-register as `admin` through the API. To make someone an admin, update
it directly in the DB:

```sql
UPDATE users SET role = 'ADMIN' WHERE email = 'someone@example.com';
```

## Main endpoints

**Auth**
- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`

**Services**
- `GET /services`
- `GET /services/{id}`
- `GET /services/{id}/available-slots?date=YYYY-MM-DD`
- `POST /services` (admin only)
- `PATCH /services/{id}` (admin only)
- `DELETE /services/{id}` (admin only)

**Appointments**
- `POST /appointments` - book one
- `GET /appointments/me?time_filter=past|upcoming` - your own appointments
- `GET /appointments?status=&date_from=&date_to=` - all appointments (admin only)
- `POST /appointments/{id}/cancel`
- `PATCH /appointments/{id}/reschedule`
