# Vase - Lab Data Management System

**Course:** Individual Software Development Process 2026
**Team:** UltraSmooth
**Challenge:** Project A - Lab Data Management

## Overview

VASE Laboratory Resource Management System is a web application for managing laboratory resources, bookings, maintenance, activity history, and user access.

The main goal is to keep laboratory information in one system and make it easier for students, lab staff, and professors to use and manage laboratory resources.

### Target Users

* **Ph.D. Students / Undergraduate Students** view resources, submit and track bookings, and check in/out resources
* **Lab Managers / Administrators** manage resources, bookings, maintenance, activity history, dashboards, and user accounts
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

### In Progress

The following features are not fully completed yet:

* Full sorting on the resource list. The current version uses the default name ordering.
* Availability-specific filtering is not available in the UI yet.
* The admin "Show Archived" option is not available in the UI yet. The backend already supports it through the `include_archived` parameter.

### Planned for Later Iterations

* **Iteration 3:** Booking and request management
* **Iteration 4:** Issue reporting and maintenance tracking
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
* **Controllers** - Handle authentication and resource-related requests
* **Models** - Handle business logic and database operations
* **Persistence** - MySQL database
* **Authentication & Authorization** - Shared middleware for authentication and role checking

More controllers will be added in later iterations as new features are implemented.

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

If the database volume already exists and does not contain the latest seed data, reset it with:

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

## Demo Login

The database is seeded with an admin account for testing:

```text
Email:    admin@ku.th
Password: Admin1234
```

This account has the `admin` role and can create, edit, and archive resources.

Five sample resources are also included in the seed data.

## Google Sign-In

Google OAuth checks the exact origin of the application, including the protocol, domain, and port.

If the application port is changed, the new origin must be added to **Authorized JavaScript origins** in Google Cloud Console.

For example, if the application runs on port `5001`:

```text
http://localhost:5001
```

It may take a few minutes for the new OAuth setting to take effect.

## Project Status

The project is currently in **Iteration 2 (Resource Management)**, covering **SRS-1** and **SRS-2**.

### Iteration 1 (Authentication & Role-Based Access)

Iteration 1 has been completed.

The implemented features include:

* Email/password login
* Google OAuth login with backend verification
* Student self-registration
* Server-side role-based access control
* Forgot and reset password

The forgot/reset password feature was added as an enhancement during the Iteration 2 work cycle.

### Iteration 2 (Resource Management)

The team completed both planned user stories within the capacity of two user stories.

#### US-1: View and Search Resources

Users can:

* Search resources by name
* Filter resources by category
* Filter resources by location
* Filter resources by status

The resource list currently uses name ordering by default.

Full sorting and a separate availability filter are still open and are tracked as **R-01**.

#### US-2: Manage Resource Records

Administrators can:

* Create resources
* Edit resources
* Validate required fields
* Validate resource status
* Archive resources

Resource archiving uses soft-delete. This means the resource is not removed from the database. Instead, it is marked as archived and hidden from the normal resource list.

The admin "Show Archived" option is not available in the UI yet, although the backend already supports the `include_archived` parameter. This is tracked as **R-02**.

### Future Iterations

The following iterations have not started yet:

* **Iteration 3:** Booking & Request Management
* **Iteration 4:** Issue Reporting & Maintenance
* **Iteration 5:** Activity History & Operations Dashboard
* **Iteration 6:** User Management

Detailed sprint information, Gantt charts, retrospective results, and the risk register are included in the Iteration Report in the `docs/` folder.

## Known Limitations

The current open issues are:

| ID   | Issue                                                                                              | Status |
| ---- | -------------------------------------------------------------------------------------------------- | ------ |
| R-01 | Full sorting and a separate availability filter are not available yet.                             | Open   |
| R-02 | The admin UI does not have a "Show Archived" option yet, although the backend already supports it. | Open   |

The team plans to complete these items before the final demonstration.

## Testing

Testing for Iteration 2 was mainly done manually and at the code level.

### US-1 Testing

We confirmed that authenticated users can:

* Search resources by name
* Filter resources by category
* Filter resources by location
* Filter resources by status

### US-2 Testing

We confirmed that:

* A resource with a missing required field is rejected with a `400` response and a validation message.
* Invalid resource status values are rejected.
* Archiving changes the resource to an archived state without deleting it from the database.
* Archived resources are hidden from the default resource list.

Automated testing and a complete SRS-to-implementation checklist are planned before the final demonstration.

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
│   │   └── resource_controller.py
│   ├── middleware/
│   │   └── auth_middleware.py
│   ├── models/
│   │   ├── user_model.py
│   │   └── resource_model.py
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
