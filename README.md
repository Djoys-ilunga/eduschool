# EduSchool — Multi-School Management Platform

**EduSchool** is a web platform for managing schools end-to-end: multiple schools on a single instance, each with its own administrators, teachers, students, parents and finances.

Built with **Python / Flask**, a modular architecture (one blueprint per domain), a REST-ready service layer and server-rendered responsive templates.

## Features

- **Multi-school** — several schools on one platform, with subscriptions & plans
- **Academic management** — academic years, trimesters, periods, classes, subjects, timetables
- **Students** — enrollments, profiles, parent links, attendance
- **Grades & report cards** — grade entry, deliberations, bulletin access control
- **Finance** — fee types, fees, school payments, receipts
- **Communication** — announcements with attachments, assignments & submissions
- **Users & RBAC** — role-based permissions (admin, school admin, teacher, student, parent)
- **Audit trail** — full audit log of sensitive actions
- **Dashboards** — per-role dashboards (platform admin, school admin, teacher, student, parent)

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask (blueprints), SQLAlchemy |
| Database | SQLite (dev) — portable to PostgreSQL / MySQL |
| Frontend | Jinja2 templates, HTML/CSS, JavaScript |
| Auth | Session-based, role-based access control |
| Email | Brevo API (transactional) |
| Deployment | Vercel (`vercel deploy`) / any WSGI host (Procfile included) |

## Project structure

```
app/
  academic/       # years, trimesters, subjects, timetables
  admin/          # platform administration
  auth/           # authentication
  communication/  # announcements, assignments
  dashboard/      # per-role dashboards
  finance/        # fees & payments
  models/         # SQLAlchemy models
  rbac/           # roles & permissions
  schools/        # school management
  students/       # students & enrollments
  users/          # user management
  utils/          # helpers
  templates/      # Jinja2 templates
app.py            # application entry point
config.py         # configuration (environment-based)
requirements.txt
```

## Getting started

```bash
git clone https://github.com/Djoys-ilunga/eduschool.git
cd eduschool
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your own values
flask run              # or: python app.py
```

> The production database and uploaded files are **not** included in this repository.

## Author

**Paul DJOMBE NTUMBA** — Full-stack developer (Python/Flask, REST APIs, SQL, Flutter), Kinshasa, DR Congo.
LinkedIn: https://www.linkedin.com/in/paul-djombe-08b9ab388/

---

*Version française : EduSchool est une plateforme web de gestion scolaire multi-écoles (années académiques, inscriptions, notes et bulletins, finances scolaires, communication école-parents), développée en Python/Flask avec une architecture modulaire et un contrôle d'accès par rôles.*
