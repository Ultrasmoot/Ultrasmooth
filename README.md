# Vase - Lab Data Management System

**Course :** Individual Software Development Process 2026
**Team :** UltraSmooth
**Challenge :** Project A - Lab Data Management

## Overview

VASE Laboratory Resource Management System is a web application for managing laboratory resources, bookings, maintenance, activity history, and user access.

The main goal is to keep laboratory information in one system and make it easier for students, lab staff, and professors to use and manage laboratory resources.

### Target Users

* **Ph.D. Students / Undergraduate Students** view resources, submit and track bookings, and check in/out resources
* **Lab Administrators** manage resources, bookings, maintenance, activity history, dashboards, and user accounts
* **Professor** view laboratory information with read-only access

## Key Features

### Completed

* Login with Google OAuth 2.0 or email/password
* Student self-registration
* Server-side role-based access control (RBAC)
* Forgot and reset password
* Time-limited and single-use password reset tokens
* Resource search by name
* Resource filtering by category, location, and status
* Admin-only resource creation and editing
* Required-field validation
* Resource status validation
* Admin-only resource archiving using soft-delete
* Archived resources remain in the database but are hidden from the default resource list
* **Booking requests** submitted by Ph.D. and Undergraduate students (US-3)
* **Booking validation:** required fields, valid dates, end time after start time, no start time in the past, purpose up to 255 characters
* **Resource availability check:** only existing, non-archived, `Available` resources can be booked
* **Overlap (conflict) check** against Pending and Approved bookings on the same resource
* **My Requests page** with Pending / Approved / Rejected status badges and automatic refresh every 30 seconds (US-4)
* **Admin review of Pending requests** with approve / reject, recording the decision, the administrator ID, and the decision time (US-5)
* **Announcements:** Professors and Administrators can post and pin/unpin announcements; all logged-in users can read them on the home page; only the author can delete an announcement
* **Rate limiting** on login, signup, and password-reset endpoints
* Application and database timezone set to `Asia/Bangkok`

### In Progress

The following items are not fully completed yet:

* Automated tests for the booking workflow (overlap, back-to-back, rejected bookings, resource status checks, concurrent requests, already-decided requests)
* Read-only view of all booking requests for Professors (access level not yet confirmed with the stakeholder)
* Replacing the in-memory rate limiter with a shared store (e.g. Redis) before final deployment
* Full sorting on the resource list, availability-specific filtering, and the admin "Show Archived" option (carried over from Iteration 2)

### Planned for Later Iterations

* **Iteration 4:** Check-in/check-out, issue reporting and maintenance tracking
* **Iteration 5:** Activity history and operations dashboard
* **Iteration 6:** User account and role management

## Tech Stack

| Layer        | Technology              |
| ------------ | ----------------------- |
| Frontend     | HTML, CSS, JavaScript   |
| Backend      | Python / Flask          |
| Architecture | MVC pattern             |
| Database     | MySQL                   |
| Environment  | Docker + Docker Compose |

## Architecture

The system uses a modular monolithic architecture with the MVC pattern.

* **View** - Web application in `frontend/index.html`
* **Controllers** - Handle authentication, resource, booking, and announcement requests
* **Models** - Handle business logic and database operations. All booking rules (validation, resource availability, conflict check) live in the Booking Model
* **Persistence** - MySQL database
* **Authentication & Authorization** - Shared middleware for authentication and role checking, used by the booking and announcement endpoints

Booking creation runs inside a database transaction that locks the selected resource row, so the conflict check and the insert happen together. Approve/reject updates a booking only while its status is still `Pending`.

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/Ultrasmoot/Ultrasmooth.git
cd Ultrasmooth
```

### 2. Set Up Environment Variables

Create a local `.env` file in the backend folder.

```bash
cd source/backend
cp .env.example .env
```

The `.env` file is ignored by Git and should not be committed.

In production (`APP_ENV=production`), the app refuses to start if `SECRET_KEY` is missing or still a placeholder.

By default, `SMTP_HOST` is empty. Password reset links are therefore printed in the container log instead of being sent by email. This is enough for local development and testing.

To send real emails, configure the following values in your local `.env` file:

```text
SMTP_HOST
SMTP_USER
SMTP_PASSWORD
SMTP_FROM
```

### 3. Start the Application

Make sure Docker Desktop is running, then:

```bash
cd source
docker compose up --build
```

The database is created and seeded automatically on the first run.

If the database volume already exists and does not contain the latest seed data (including the Iteration 3 `bookings` and `announcements` tables), reset it with:

```bash
docker compose down -v
docker compose up --build
```

> **Warning:** `docker compose down -v` removes the existing database volume.

### 4. Open the Application

Open the following address in your browser:

**http://localhost:5000**

If port `5000` is already in use, change the host-side port in `docker-compose.yml`.

For example:

```yaml
"5001:5000"
```

Then open:

**http://localhost:5001**

The container-side port remains `5000`.

## Project Status

The project is currently in **Iteration 3 (Booking & Request Management)**, covering **SRS-3**, **SRS-4** and **SRS-5**.

### Iteration 1 (Authentication & Role-Based Access)

Iteration 1 has been completed.

The implemented features include:

* Email/password login
* Google OAuth login with backend verification
* Student self-registration
* Server-side role-based access control
* Forgot and reset password

### Iteration 2 (Resource Management)

Iteration 2 has been completed (SRS-1 and SRS-2).

* **US-1:** Users can search resources by name and filter by category, location, and status.
* **US-2:** Administrators can create, edit, validate, and archive resources. Archiving uses soft-delete.

### Iteration 3 (Booking & Request Management)

The team completed all three planned user stories. Capacity was three stories, one more than in Iterations 1 and 2, because all three share the same `bookings` table and Booking Model.

#### US-3: Submit a Booking Request

Ph.D. and Undergraduate students can choose a resource, start time, end time, and purpose.

The system rejects:

* Empty required fields
* An end time that is not after the start time
* A start time in the past
* A purpose longer than 255 characters
* A resource that does not exist, is archived, or is not `Available`
* A request that overlaps a Pending or Approved booking on the same resource

Rejected bookings do not block a slot, and back-to-back bookings are allowed. Other roles are refused. The form shows the error message returned by the server.

#### US-4: Track My Bookings/Requests

Students can view only their own booking requests with Pending, Approved, or Rejected badges. The list is sorted by start time, latest first. It can be refreshed manually and reloads automatically every 30 seconds while the Requests page is open and visible.

#### US-5: Review and Approve/Reject Requests

Administrators can view Pending requests (resource name, requester name and email, earliest start time first) and approve or reject each one. The system records the decision, the administrator ID, and the decision time. A request that has already been decided cannot be decided again, even if two administrators act at the same moment.

#### Scope Addition: Announcements

Added as a small extension with no user story removed. Professors and Administrators can post and pin/unpin announcements, all logged-in users can read them on the home page (pinned first), and only the author can delete an announcement.

### Future Iterations

The following iterations have not started yet:

* **Iteration 4:** Check-in/Check-out & Maintenance
* **Iteration 5:** Activity History & Operations Dashboard
* **Iteration 6:** User Management

Detailed sprint information, Gantt charts, retrospective results, and the risk register are included in the Iteration Report in the `docs/` folder.

## Known Limitations

The current open issues are:

| ID   | Issue                                                                                                                                      | Status     |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------- |
| R-01 | Double booking: concurrency tests are still needed to confirm simultaneous requests cannot create conflicting bookings.                    | Open       |
| R-02 | Professors have no read-only view of all booking requests, and the access level each role needs is not yet confirmed.                      | Open       |
| R-03 | Availability checks are not yet tested against resources that are In Use, under Maintenance, or archived.                                  | Open       |
| R-04 | The rate limiter keeps counters in memory (per process, reset on restart). A shared store such as Redis is needed before final deployment. | Open       |
| R-05 | Date/time values without a timezone offset are treated as server-local time. `TZ=Asia/Bangkok` must be kept in Docker settings.            | Monitoring |

## Testing

Automated tests are in `backend/tests/test_security.py`. They cover Google sign-in validation, rate limiting, signup input validation, password-reset token handling, and production secret-key configuration. **They do not yet cover the booking workflow.**

The Iteration 3 implementation was reviewed by the team for input validation, resource availability, conflict detection, and transaction handling.

### US-3 Review

* Missing or blank fields, invalid dates, end times not after start times, past start times, and purposes over 255 characters are rejected.
* The selected resource must exist, not be archived, and have an `Available` status.
* Date/time values with a timezone offset are converted to server time; values without an offset are treated as server-local time.
* Only Pending and Approved bookings count as conflicts.

### US-4 Review

* The system returns only bookings that belong to the logged-in user.

### US-5 Review

* Only administrators can open the Pending list and the decide endpoint.
* Only `approve` or `reject` are accepted as a decision.
* An already-decided request cannot be decided again.

### Announcements Review

* Empty title or body is rejected.
* Only the author can delete an announcement.

### Planned Tests (before Iteration 4)

* Booking validation
* Overlap check: partial overlap, back-to-back, and a rejected booking freeing the slot
* Resource availability: In Use, Maintenance, archived
* Concurrent booking requests
* Approve/reject, including an already-decided request

## Project Structure

```text
source/
├── .gitignore
├── docker-compose.yml
├── backend/
│   ├── app.py
│   ├── config.py
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   ├── controllers/
│   │   ├── auth_controller.py
│   │   ├── resource_controller.py
│   │   ├── booking_controller.py
│   │   └── announcement_controller.py
│   ├── middleware/
│   │   └── auth_middleware.py
│   ├── models/
│   │   ├── user_model.py
│   │   ├── resource_model.py
│   │   ├── booking_model.py
│   │   └── announcement_model.py
│   ├── tests/
│   │   └── test_security.py
│   └── database/
│       ├── db.py
│       ├── schema.sql
│       └── seed.sql
└── frontend/
    └── index.html
```

## Team Members

| Name                  | Student ID |
| --------------------- | ---------- |
| Jirat Kiattrairong    | 6810545506 |
| Napakhet Namsrioun    | 6810545727 |
| Panyasiri Aimngern    | 6810545743 |
| Panisara Niyathirakul | 6810545751 |
