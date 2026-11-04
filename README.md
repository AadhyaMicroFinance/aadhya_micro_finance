# Finance & Chitti Management System

A production-ready Finance and Chitti (community savings) management system with backend API, web dashboard, and mobile application.

## Architecture

```
finance-chitti-system/
├── backend/          # FastAPI + SQLAlchemy + PostgreSQL
├── web/              # Next.js + React + TypeScript + Tailwind
├── mobile/           # React Native + TypeScript
├── docker/           # Docker Compose for local development
└── docs/             # Architecture documentation
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.x, Alembic |
| Database | PostgreSQL 16 |
| Cache/Queue | Redis 7 |
| Background Jobs | Celery |
| Auth | JWT (jose) + Argon2 |
| Web Frontend | Next.js 14, React, TypeScript, Tailwind CSS |
| Mobile | React Native, TypeScript |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.12+
- Node.js 20+

### 1. Start with Docker (Recommended)

```bash
cd docker
docker-compose up -d
```

This starts:
- Backend API at http://localhost:8000
- API docs at http://localhost:8000/docs (debug mode)
- Web app at http://localhost:3000
- PostgreSQL at localhost:5432
- Redis at localhost:6379
- Celery worker
- Celery beat scheduler

### 2. Backend Development (without Docker)

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start PostgreSQL and Redis first, then:
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 3. Run Tests

```bash
cd backend
pytest -v
```

## User Roles

| Role | Capabilities |
|------|-------------|
| SUPER_ADMIN | Full access: users, roles, settings, all data |
| ADMIN | Manage customers, finance, chitti, payments, reports |
| STAFF | Add customers, record payments, view schedules |
| COLLECTOR | View assigned customers, record payments |

## API

All APIs are versioned under `/api/v1/`.

See `docs/api-reference.md` for complete API documentation.

### Key Endpoints

- `POST /api/v1/auth/login` - Authenticate
- `POST /api/v1/customers/` - Create customer
- `POST /api/v1/finance/` - Create finance account
- `POST /api/v1/payments/` - Record payment
- `GET /api/v1/reports/daily` - Daily collection report

## Database

- 13 tables with proper foreign keys and indexes
- UUID primary keys
- Immutable payment ledger
- Audit trail for all mutations
- Run migrations: `alembic upgrade head`

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

**Never commit `.env` to version control.**

## Development Phases

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Project structure, Docker, backend foundation |
| Phase 2 | 🔲 Pending | Authentication & Users |
| Phase 3 | 🔲 Pending | Customer module |
| Phase 4 | 🔲 Pending | Finance module |
| Phase 5 | 🔲 Pending | Chitti module |
| Phase 6 | 🔲 Pending | Payment system refinement |
| Phase 7 | 🔲 Pending | Reports & Dashboard |
| Phase 8 | 🔲 Pending | WhatsApp integration |
| Phase 9 | 🔲 Pending | Celery scheduler |
| Phase 10 | 🔲 Pending | Mobile collector workflow |
| Phase 11 | 🔲 Pending | Audit logs |
| Phase 12 | 🔲 Pending | Security hardening |
| Phase 13 | 🔲 Pending | Production Docker |

## License

Proprietary. Internal use only.
