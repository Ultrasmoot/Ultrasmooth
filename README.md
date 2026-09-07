# VASE Laboratory Resource Management System

**Course:** Individual Software Development Process 2026  
**Team:** UltraSmooth  
**Challenge:** Project A - Lab Data Management

## Overview

This is a centralized system for managing the VASE Software Engineering Laboratory's resources, bookings, maintenance, activity history, and user access. It is designed to replace fragmented manual tools with one consistent platform.

### Target Users
- **Ph.D. Students / Undergraduate Students** — view resources, submit and track bookings, and check in/out resources
- **Lab Managers / Administrators** — manage resources, bookings, maintenance, activity logs, dashboards, and user accounts
- **Professor** — read-only access to all laboratory information

## Key Features
- Resource search, filtering, and management (create/edit/archive)
- Booking and request submission with conflict checking
- Issue reporting and maintenance tracking
- Activity history with filtering
- Operations dashboard 
- Resource check-in / check-out using a resource code
- Authentication via Google OAuth 2.0 or email/password
- Role-based access control (RBAC)
- User account and role management

## Tech Stack
| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python (MVC pattern) |
| Database | MySQL |
| Environment | Docker + Docker Compose |

## Architecture

The system uses a modular monolithic architecture with the MVC pattern:

- **View** — Web Application
- **Controllers** — Resource, Booking & Check-in/Check-out, Maintenance, History & Dashboard
- **Models** — Business logic for each domain
- **Persistence** — Laboratory Database (MySQL)
- **Cross-cutting** — Authentication & Authorization module

## Getting Started

```bash
# Clone the repository
git clone <repo-url>
cd <repo-name>

# Start the application and database with Docker Compose
docker compose up --build
```

> Requires Docker Desktop to be installed locally.

## Project Status

The project is currently in **Iteration 1 — Authentication & Access** (SRS-11, SRS-12).

- **Completed:** Login page (email/password + Google OAuth frontend flow), self-registration for student accounts, and role-based view logic on the frontend (users can only access pages and features allowed for their roles)
- **In progress:** Backend OAuth callback and token verification, backend login validation against the database, and backend-enforced authorization
- **Not started yet:** Iteration 2 (Resource Management) through Iteration 6 (User Management) — see the critical path in the Iteration Report

Full sprint details, Gantt charts, retrospective, and the risk register are included in the Iteration Report (see table below).

## Project Structure

- [README.md](README.md)
- [.gitignore](.gitignore)
- **docs/**
  - [SRS.pdf](docs/SRS.pdf)
  - [Software-Proposal.pdf](docs/Software-Proposal.pdf)
  - [isp-ultrasmooth-sprint1.pdf](docs/isp-ultrasmooth-sprint1.pdf)
  - [Gratt_Chart.json](docs/Gratt_Chart.json)
  - [use-case-diagrams.json](docs/use-case-diagrams.json)
- **source/**
  - [VASE-frontend.html](source/VASE-frontend.html)

## Team Members
| Name | Student ID |
|---|---|
| Jirat Kiattrairong | 6810545506 |
| Napakhet Namsrioun | 6810545727 |
| Panyasiri Aimngern | 6810545743 |
| Panisara Niyathirakul | 6810545751 |
