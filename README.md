# Vase - Lab Data Management System

**Course :** Individual Software Development Process 2026 **Team :**
UltraSmooth **Challenge :** Project A - Lab Data Management

## Overview

VASE Laboratory Resource Management System is a web application for
managing laboratory resources, bookings, maintenance, activity history,
and user access.

The main goal is to keep laboratory information in one system and make
it easier for students, lab staff, and professors to use and manage
laboratory resources.

### Target Users

-   **Ph.D. Students / Undergraduate Students** view resources, submit,
    track, and cancel bookings, check in/out resources, report issues,
    and request appointments with professors
-   **Lab Administrators** manage resources, bookings, maintenance, user
    accounts and roles, and can read the activity log and dashboard
-   **Professors** read the activity log and dashboard, post
    announcements, and answer appointment requests

## Key Features

### Iteration 1 - Authentication & Access (SRS-11, SRS-12)

-   Login with Google OAuth 2.0 (verified on the backend) or
    email/password
-   Student self-registration with e-mail verification
-   Server-side role-based access control (RBAC)
-   Forgot and reset password with time-limited, single-use tokens
-   Rate limiting on login, signup, and password-reset endpoints

### Iteration 2 - Resource Management (SRS-1, SRS-2)

-   Resource search by name; filters by category, location, and status
-   Admin-only resource creation and editing with required-field and
    status validation
-   Sorting on the resource list
-   Admin-only archiving (soft-delete); archived resources stay in the
    database but are hidden from the default list, and admins can show
    archived resources

### Iteration 3 - Booking & Request Management (SRS-3, SRS-4, SRS-5)

-   **US-3:** booking requests with validation (required fields, valid
    dates, end after start, no start in the past, purpose up to 255
    characters); only existing, non-archived, `Available` resources can
    be booked; overlap check against Pending and Approved bookings
    (back-to-back is allowed, rejected bookings free the slot)
-   **US-4:** My Requests page with status badges and automatic refresh
    every 30 seconds
-   **US-5:** admin approve / reject, recording the decision, the
    administrator ID, and the decision time
-   Announcements: professors and admins post and pin/unpin; everyone
    reads them on the home page; only the author deletes

### Iteration 4 - Check-in/Check-out & Maintenance (SRS-10, SRS-6, SRS-7)

-   **US-10:** check-in with a one-time code sent by e-mail, and
    check-out
-   **US-6:** every role can report a resource issue
-   **US-7:** administrators edit, confirm, dismiss, and resolve
    maintenance records

### Iteration 5 - Activity Log, Dashboard & User Management (SRS-8, SRS-9, SRS-13)

-   **US-8:** activity log (administrators and professors, read-only)
    with filters by date range, user, action type, and resource; 20
    entries per page, newest first; each row is saved in the same
    transaction as the action; records older than 45 days are deleted by
    default
-   **US-9:** operations dashboard (administrators and professors):
    resources by status, active bookings, pending requests, open issues,
    and utilization per category over 7, 30, 90 days or a custom range
-   **US-13:** administrators list, create, edit, deactivate, and
    reactivate users and change roles. A deactivated account cannot log
    in and its token stops working at once. An administrator cannot
    deactivate or demote themselves, and the last active administrator
    is always protected
-   Added in this iteration without dropping a story:
    -   **Automatic check-out** 20 minutes after the booking ends
        (`AUTO_CHECKOUT_GRACE_MINUTES`, 0-240), with a notification and
        a log entry
    -   **Cancel a booking** by the student (Pending, or Approved and
        not yet used)
    -   Notification bell, resource detail page, and appointments with
        professors

### Iteration 6 - Code Refactoring

No new features. The behaviour of the system is unchanged.

-   Code reorganised into one folder per feature in `controllers/`,
    `models/`, and `tests/`, and into `pages/` and `static/` in the
    frontend
-   Large files split into small, focused modules; shared helpers moved
    to `services/`, `middleware/`, and `web/`
-   Test files renamed to say what they check, and grouped by feature
-   Maintainability Index checked for every `.py` file using the formula
    from the course
-   Documented the known limitations (see below)

US-13 was moved into Iteration 5 so that the plan has five feature
iterations plus this refactoring iteration.

### Other

-   Application and database timezone set to `Asia/Bangkok`

## Tech Stack

| Layer        | Technology              |
| ------------ | ----------------------- |
| Frontend     | HTML, CSS, JavaScript   |
| Backend      | Python / Flask          |
| Architecture | MVC pattern             |
| Database     | MySQL 8                 |
| Environment  | Docker + Docker Compose |

## Architecture

The system uses a modular monolithic architecture with the MVC pattern,
organised by feature.

-   **View** - `frontend/index.html` loads page fragments from
    `frontend/pages/` and scripts and styles from `frontend/static/`
-   **Controllers** - `backend/controllers/<feature>/` handle HTTP
    requests
-   **Models** - `backend/models/<feature>/` hold business rules and
    database operations
-   **Services** - `backend/services/`: `mailer`, `locking`, `events`
    (activity log helper), `housekeeping` (automatic check-out and
    old-record cleanup)
-   **Middleware** - `backend/middleware/`: authentication, role
    checking, rate limiting
-   **Web helpers** - `backend/web/`: security headers and error
    handlers
-   **Persistence** - MySQL; `backend/database/` holds `schema.sql`,
    `seed.sql`, and `migrations/`

All modules lock the resource row first, then the booking (and
administrator rows first for user changes), so concurrent actions cannot
create a double booking or leave the lab without an administrator.
Approve/reject only updates a booking while its status is still
`Pending`.

## Getting Started

This guide explains how to set up, run, configure, and test the VASE Lab
Data Management System.

## 1. Quick Start

Follow these steps to run the application locally.

### Prerequisites

-   Git
-   Docker Desktop (make sure Docker Engine is running)

### Step 1: Clone the Repository

``` bash
git clone https://github.com/Ultrasmoot/Ultrasmooth.git
cd Ultrasmooth
```

### Step 2: Set Up Environment Variables

Navigate to the backend directory and create your local environment
file:

``` bash
cd source/backend
cp .env.example .env
```

Open `.env` in a text editor and check the following settings:

``` env
APP_ENV=development
SECRET_KEY=change-me-to-a-long-random-string
DB_HOST=db
DB_PORT=3306
DB_USER=vase_user
DB_PASSWORD=vase_pass
DB_NAME=vase_lab
```

The default values copied from `.env.example` work for local development
without changes. With `APP_ENV=development`, the placeholder `SECRET_KEY`
is accepted. If `APP_ENV` is not set, it defaults to `production`, and the
application refuses to start while `SECRET_KEY` is missing or still a
placeholder. If you change the database settings, make sure they match
the corresponding `MYSQL_*` values in `source/docker-compose.yml`.

Save the file before proceeding.

### Step 3: Start the Application

Navigate to the `source` directory:

``` bash
cd ..
docker compose up --build
```

Wait until the database is healthy and the Flask application starts
successfully.

### Step 4: Open the Application

Open the application in your browser:

[**http://localhost:5000**](http://localhost:5000)

### Step 5: Sign In

Use one of the demo accounts listed at the top of:

`source/backend/database/seed.sql`

These accounts are for local demonstration and testing only.

------------------------------------------------------------------------

## 2. Configuration

This section explains optional settings for customizing the local
environment.

### Environment Variables

The environment file is located at:

`source/backend/.env`

| Variable | Description |
| -------- | ----------- |
| `APP_ENV` | Application environment (`development` or `production`) |
| `SECRET_KEY` | Secret key used by the application |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | Database connection settings; must match the `MYSQL_*` values in `source/docker-compose.yml` |
| `ALLOWED_EMAIL_DOMAIN` | E-mail domain allowed for registration (default: `ku.th`) |
| `AUTO_CHECKOUT_GRACE_MINUTES` | Minutes after a booking ends before automatic check-out (default: `20`, range: 0-240) |
| `ACTIVITY_RETENTION_DAYS`, `NOTIFICATION_RETENTION_DAYS` | Retention periods for activity logs and notifications (default: `45`; `0` keeps everything) |
| `APP_BASE_URL` | Base address used in e-mail links (default: `http://localhost:5000`) |
| `GOOGLE_CLIENT_ID` | Optional Google OAuth client ID |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Optional SMTP settings for sending e-mails |

The `.env` file contains sensitive configuration values. Do not commit
or share it.

For production, set a strong random `SECRET_KEY`. You can generate one
with:

``` bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### E-mail Configuration

By default, `SMTP_HOST` is empty. The application does not send real
e-mails; instead, verification links, password reset links, and check-in
codes are printed in the application logs.

To send e-mails using Gmail:

1.  Enable 2-Step Verification for the Google account.
2.  Create an App password in the Google account security settings.
3.  Configure the following values in `source/backend/.env`:

``` text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-address@gmail.com
SMTP_PASSWORD=the-16-character-app-password
SMTP_FROM=your-address@gmail.com
```

Use the App password, not the normal Gmail password.

After changing the SMTP settings, restart the application from the
`source` directory:

``` bash
docker compose up -d --force-recreate app
```

### Google Sign-in Configuration

To enable Google sign-in:

1.  Create an OAuth client ID with the type **Web application** in
    Google Cloud Console.
2.  Add the application address (for example, `http://localhost:5000`)
    under **Authorized JavaScript origins**.
3.  Set `GOOGLE_CLIENT_ID` in `source/backend/.env`.

Leave `GOOGLE_CLIENT_ID` empty to disable Google sign-in.

------------------------------------------------------------------------

## 3. Application Management

### View Application Logs

To view the latest application logs, open a separate terminal and
navigate to the repository's `source` directory:

``` bash
cd path/to/Ultrasmooth/source
```

Replace `path/to/Ultrasmooth` with the actual location of your cloned
repository.

Run:

``` bash
docker compose logs app --tail 50
```

To continuously monitor new log messages:

``` bash
docker compose logs -f app
```

Press `Ctrl + C` to stop viewing logs without stopping the application.

Logs are useful for checking application errors and retrieving
verification links, password reset links, and check-in codes when SMTP
is not configured.

### Stop the Application

If the application is running in the foreground, press:

``` text
Ctrl + C
```

Then, from the `source` directory, run:

``` bash
docker compose down
```

This stops and removes the application containers and network while
preserving the database volume.

### Reset the Database

To recreate the database from scratch, run the following commands from
the `source` directory:

``` bash
docker compose down -v
docker compose up --build
```

**Warning:** `docker compose down -v` permanently deletes the database
volume and all data stored in it. Only use this command when the
existing data is no longer needed.

To preserve existing data, apply the files in
`backend/database/migrations/` in numeric order. Follow the instructions
at the top of each migration file.

### Change the Application Port

If port `5000` is already in use, edit the port mapping in
`source/docker-compose.yml`.

For example:

``` yaml
ports:
  - "5001:5000"
```

Then restart the application and open:

**http://localhost:5001**

The container-side port remains `5000`.

### Troubleshooting

**Docker Engine is not running**

If you see an error such as:

``` text
failed to connect to the docker API
```

Open Docker Desktop and wait until the Docker Engine is ready. Then
retry the Docker Compose command.

**Database container is unhealthy**

Inspect the database logs:

``` bash
docker compose logs db --tail 100
```

If the error indicates an incompatible MySQL data directory, check the
MySQL image version and existing database volume. Do not attempt to
downgrade the database. For a fresh local setup where existing data can
be deleted, use the Reset the Database instructions above.

**Application fails to start**

If the application reports `ModuleNotFoundError`, check that the module
or package exists and that its directory and file names match the Python
import statements. If the problem persists, report it to the project
maintainers.

------------------------------------------------------------------------

## 4. Testing

Backend tests are divided into unit tests and MySQL integration tests.

### Backend Unit Tests

These tests do not require a MySQL database. Tests that need a real
MySQL database are skipped.

From the repository root:

``` bash
cd source/backend
python -m unittest discover -s tests -v
```

### MySQL Integration Tests

Tests that require a real MySQL database, such as row locking,
`lastrowid`, and the demo seed, run in a separate test database.

From the repository root, navigate to the `source` directory:

``` bash
cd source
```

Run the integration tests:

``` bash
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
```

After the tests finish, remove the test containers and database volume:

``` bash
docker compose -f docker-compose.test.yml down -v
```

**Warning:** This cleanup command removes the test database volume. Do
not use it to clean up the main application database.

Backend tests are grouped by feature in
`backend/tests/<feature>_tests/`. The Iteration 5 report (section 5)
describes the test coverage.

## Known Limitations

| ID   | Issue | Status |
| ---- | ----- | ------ |
| R-01 | **Double booking / double confirmation.** Row locks should prevent it, but no test sends parallel requests. The locking tests run on SQLite, which has no real row locks. Two-thread tests on real MySQL are needed before deployment. | Open |
| R-02 | **Rate limiter.** Counters are kept in memory (per process, reset on restart, not shared between workers). Use Redis or Flask-Limiter before a multi-worker deployment. The 3-attempt check-in limit is already stored in the database. | Open |
| R-03 | **Check-in depends on SMTP.** If the mail server is down, students cannot check in. | Open |
| R-05 | **Log retention.** Old log and notification rows are deleted after 45 days (changeable in settings, 0 keeps everything). The required retention time is still to be confirmed with the stakeholder. | Open |
| R-07 | **`lastrowid`.** The code reads `cursor.lastrowid` right after `INSERT`. The regression tests use a fake DB, so this has not been checked on real MySQL. | Open |
| R-08 | **Background worker.** Automatic check-out starts inside the web process (`start_background_worker()` in `app.py`) and the Dockerfile runs one `python app.py`. Run the app with **one worker**. With several workers each one runs the job; this is safe because every booking is locked and checked again, but it is not clean. | By design |
| R-09 | **Timezone.** Date/time values without a timezone offset are treated as server-local time. Keep `TZ=Asia/Bangkok` in the Docker settings. | Monitoring |

Closed risks: R-04 (forgotten check-out, handled by automatic check-out)
and R-06 (lab left without an administrator, handled by the server rules
above).

Detailed sprint information, Gantt charts, retrospectives, and the full
risk register are in the iteration reports in the `docs/` folder.

## Project Structure

``` text
Ultrasmooth/
├── README.md
├── docs/                         SRS, proposal, iteration reports, diagrams
└── source/
    ├── docker-compose.yml
    ├── docker-compose.test.yml
    ├── backend/
    │   ├── app.py
    │   ├── config.py
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   ├── .env.example
    │   ├── controllers/<feature>/   activity, announcement, appointment, auth, booking,
    │   │                            calendar, checkin, dashboard, history, maintenance,
    │   │                            notification, resource, user_admin
    │   ├── models/<feature>/        same features + resource_detail, user
    │   ├── services/                events, housekeeping, locking, mailer
    │   ├── middleware/              authentication, roles, rate limiting
    │   ├── web/                     security headers, error handlers
    │   ├── database/                db.py, schema.sql, seed.sql, migrations/
    │   └── tests/                   <feature>_tests/ and support/
    └── frontend/
        ├── index.html
        ├── pages/                   auth, layout, views
        └── static/                  css, js
```

## Team Members

| Name                  | Student ID |
| --------------------- | ---------- |
| Jirat Kiattrairong    | 6810545506 |
| Napakhet Namsrioun    | 6810545727 |
| Panyasiri Aimngern    | 6810545743 |
| Panisara Niyathirakul | 6810545751 |
