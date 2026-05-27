# Prominence Bank – Core Banking & Digital Banking Platform

A full-stack **core-banking demo** that explores how a digital bank works under the hood: a double-entry ledger engine, multi-currency accounts, OTP two-factor authentication, maker-checker approval workflows, KYC/AML controls, bank-instrument issuance, and an immutable audit trail. Built as a portfolio project to go deep on the parts that make financial software hard — correctness, concurrency, security and auditability.

![Django](https://img.shields.io/badge/Django-5.1-092E20?logo=django)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)
![License](https://img.shields.io/badge/License-Proprietary-red)

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & Docker Compose
- Git

### Launch (Single Command)

```bash
git clone https://github.com/julianbecerra13/prominence-bank-platform.git
cd prominence-bank-platform
cp .env.example .env
docker compose up --build -d
```

Containers seed themselves on first boot. If you need to (re)seed manually:

```bash
docker compose exec backend python manage.py migrate --noinput
docker compose exec backend python manage.py seed_demo --no-input
```

### Access

| Service | URL |
|---------|-----|
| **Client Portal** | http://localhost:3000 |
| **Admin Back Office** | http://localhost:3000 (login as admin) |
| **API** | http://localhost:8000/api/v1/ |

### Demo Credentials

| Role | Email | Password |
|------|-------|----------|
| Admin Manager | `admin@prominencebank.com` | `Admin2026!Secure` |
| Admin Operator | `operator@prominencebank.com` | `Operator2026!Secure` |
| Admin Viewer (read-only) | `viewer@prominencebank.com` | `Viewer2026!Secure` |
| Client – John Doe | `john.doe@email.com` | `Client2026!Secure` |
| Client – Maria Santos | `maria.santos@globalcorp.com` | `Client2026!Secure` |

> **OTP:** In demo mode, the OTP code is displayed as a toast notification on the login screen. No email/SMS required.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                        │
│                                                          │
│  ┌──────────┐  ┌──────────────┐  ┌────────┐  ┌───────┐ │
│  │ Frontend │  │   Backend    │  │ Postgres│  │ Redis │ │
│  │ React 18 │──│ Django 5 +   │──│   16    │  │   7   │ │
│  │ Vite     │  │ DRF          │  │         │  │       │ │
│  │ Tailwind │  │              │  │         │  │       │ │
│  │ :3000    │  │ :8000        │  │ :5432   │  │ :6379 │ │
│  └──────────┘  └──────────────┘  └────────┘  └───────┘ │
└─────────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12, Django 5.1, Django REST Framework 3.15 |
| **Frontend** | React 18, Vite 6, Tailwind CSS 3.4, Recharts |
| **Database** | PostgreSQL 16 (ACID, transactional integrity) |
| **Cache** | Redis 7 |
| **Auth** | JWT (SimpleJWT) + Email OTP two-factor |
| **PDF** | ReportLab |
| **Deployment** | Docker / Docker Compose |
| **OS** | Ubuntu Linux (containers) |

---

## Platform Modules

### 1. Core Banking Ledger Engine
- **Double-entry accounting** – every financial operation creates exactly 2 ledger entries (debit + credit)
- **Balance types:** Available, Held, In-Transit – tracked independently per account
- **Immutable ledger entries** – no updates or deletes; corrections via reversal entries only
- **Deterministic balance rebuild** – balances can be recalculated from ledger entries at any time

### 2. Client Web Banking Portal
- Dashboard with balance summaries, charts (Recharts), and recent activity
- Multi-account view (checking, savings, crypto, custody)
- Transaction history with search and filtering
- Beneficiary management (add, view, manage external payees)
- Wire transfer requests (submitted for admin approval)
- Funding instructions display (bank-configured per account)
- PDF statement generation and download
- Bank instruments view (CD, SBLC, Bank Guarantee, etc.)

### 3. Admin & Operations Back Office
- **Customer Management:** Create, view, search customers with KYC workflow
- **KYC Approval:** Pending → Approved / Rejected with audit trail
- **Account Management:** Open accounts (checking, savings, crypto, custody), freeze/unfreeze
- **Deposits:** Post deposits with real-time balance updates and double-entry confirmation
- **Holds:** Place/release holds – available balance decreases, held balance increases, ledger stays constant
- **Transfer Approvals:** Maker-checker workflow requiring two different admin users
- **Instruments:** Issue CD, SBLC, Bank Guarantee, SKR, BCC, POF, KTT, Bank Draft, Block Funds
- **Audit Logs:** Immutable, filterable, searchable log of every system action

### 4. Bank Instruments (9 Types)
| Code | Instrument |
|------|-----------|
| CD | Certificate of Deposit |
| SBLC | Standby Letter of Credit |
| BG | Bank Guarantee |
| SKR | Safe Keeping Receipt |
| BCC | Bank Certified Check |
| POF | Proof of Funds |
| KTT | Key Tested Telex |
| BD | Bank Draft |
| BF | Block Funds |

Admin creates instrument types and issues instruments to customers. Clients see their issued instruments in the portal. Expandable catalog – new types can be added without code changes.

### 5. Security & Authentication
- Password + Email OTP required for login
- JWT access + refresh tokens with automatic rotation
- Password policy: minimum 10 characters, complexity enforced
- Account lockout after 5 failed login attempts (30-minute cooldown)
- OTP: single-use, SHA-256 hashed storage, 10-minute expiry, rate-limited
- Session timeout via JWT expiry (30 minutes access, 12 hours refresh)
- Force logout on credential change
- TLS-ready configuration

### 6. RBAC (Role-Based Access Control)
| Role | Permissions |
|------|------------|
| **Superadmin** | Full access to all modules |
| **Admin Manager** | Create, approve, manage all operations |
| **Admin Operator** | Create, deposit, approve (cannot approve own reviews) |
| **Admin Viewer** | Read-only access to all admin modules |
| **Client** | Access own accounts, transactions, beneficiaries, transfers |

### 7. Maker-Checker Workflow
Wire transfer approval requires **two different admin users**:
1. **Reviewer** marks transfer as "under review"
2. **Approver** (must be a different user) approves or rejects

The system enforces that the same user cannot both review and approve a transfer.

### 8. Audit & Compliance
- **Immutable audit logs** – `save()` blocks updates, `delete()` raises errors
- **Automatic logging** via Django signals on all models
- Every action recorded: deposits, holds, transfers, KYC decisions, instrument issuance
- Logs include: timestamp, user, action, resource, IP address, change details
- Filterable by action type, searchable by description

---

## API Reference

Base URL: `http://localhost:8000/api/v1/`

### Authentication
```
POST /auth/login/          → { email, password } → OTP sent
POST /auth/verify-otp/     → { email, otp_code } → JWT tokens
POST /auth/refresh/        → { refresh }         → new access token
POST /auth/logout/         → { refresh }         → token blacklisted
GET  /auth/me/             → current user info
```

### Client Portal
```
GET  /client/dashboard/
GET  /client/accounts/
GET  /client/accounts/{id}/transactions/
GET  /client/accounts/{id}/funding-instructions/
GET  /client/accounts/{id}/statement/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
GET  /client/beneficiaries/
POST /client/beneficiaries/
GET  /client/transfers/
POST /client/transfers/
GET  /client/instruments/
```

### Admin Back Office
```
# Customers
GET/POST     /admin/customers/
POST         /admin/customers/{id}/approve_kyc/
POST         /admin/customers/{id}/reject_kyc/

# Accounts
GET/POST     /admin/accounts/

# Financial Operations
POST         /admin/deposits/
POST         /admin/hold-place/
POST         /admin/hold-release/{id}/
POST         /admin/adjustments/

# Transfer Approvals
GET          /admin/transfers/
POST         /admin/transfers/{id}/review/
POST         /admin/transfers/{id}/approve/
POST         /admin/transfers/{id}/reject/

# Instruments
GET/POST     /admin/instrument-types/
GET/POST     /admin/instruments/

# Audit
GET          /admin/audit-logs/
```

---

## Project Structure

```
prominence-bank/
├── docker-compose.yml
├── .env.example
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── manage.py
│   ├── config/                    # Django settings, URLs, WSGI
│   └── apps/
│       ├── accounts/              # User model, JWT auth, OTP
│       ├── customers/             # Customer profiles, KYC workflow
│       ├── banking/               # Ledger engine, accounts, deposits, holds
│       ├── transfers/             # Beneficiaries, wire requests, maker-checker
│       ├── instruments/           # Bank instruments CRUD
│       ├── statements/            # PDF generation (ReportLab)
│       ├── audit/                 # Immutable audit logs, signals
│       └── core/                  # Base models, RBAC, seed data
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── components/            # DataTable, Modal, StatCard, etc. (14 shared)
│       ├── layouts/               # ClientLayout, AdminLayout
│       ├── pages/
│       │   ├── auth/              # Login, OTP verification
│       │   ├── client/            # Dashboard, Transactions, Wire, Statements...
│       │   └── admin/             # Customers, Accounts, Deposits, Holds...
│       ├── context/               # AuthContext (JWT + role management)
│       └── api/                   # Axios client with token refresh
│
└── scripts/
    └── test_all.sh                # Automated test suite (55 tests)
```

---

## Testing & CI

Two complementary layers:

**1. Unit tests (pytest + pytest-django)** — fast, isolated tests on in-memory SQLite that verify the ledger invariants directly, with no running server:

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

They assert the properties that matter for a ledger: every transaction is a balanced double entry (debits == credits), holds move money between balance buckets without changing the total, transfers conserve money across accounts, an account cannot be overdrawn, ledger entries are immutable, and money operations are idempotent under retries.

**2. Integration smoke script** — `scripts/test_all.sh` drives the full HTTP API against a running, seeded server (auth, KYC, deposits, holds, maker-checker, RBAC, multi-tenant isolation). Requires `bash`, `curl` and `node`:

```bash
bash scripts/test_all.sh
```

**Continuous integration** — `.github/workflows/ci.yml` runs the pytest suite and `python manage.py check --deploy` (Django's deployment security checklist) on every push.

---

## Demo Walkthrough

### Admin Flow (Back Office)
1. Login as `admin@prominencebank.com` → enter OTP from toast
2. **Customers** → Create new customer → Approve KYC
3. **Accounts** → Open checking account for customer
4. **Deposits** → Deposit $100,000 → observe balance update in real-time
5. **Holds** → Place $30,000 hold → available decreases, held increases, ledger unchanged
6. **Holds** → Release hold → balance restored
7. **Instruments** → Issue SBLC to customer
8. **Audit Logs** → Every action logged with timestamp, user, IP

### Client Flow (Portal)
1. Login as `john.doe@email.com` → enter OTP
2. **Dashboard** → Balance charts, account overview, recent transactions
3. **Beneficiaries** → Add external payee
4. **Wire Transfer** → Submit $5,000 transfer request (goes to pending)
5. **Statements** → Download PDF statement
6. **Instruments** → View issued Certificate of Deposit

### Maker-Checker Demo
1. Admin Manager reviews transfer → status: "under review"
2. Same admin tries to approve → **BLOCKED** (maker-checker enforced)
3. Admin Operator approves → transfer completed, balance deducted

---

## Deployment (Production)

```bash
# Production build
docker-compose -f docker-compose.yml up --build -d

# Environment variables (set in .env)
DB_PASSWORD=<strong-password>
SECRET_KEY=<django-secret-key>
DEBUG=0
ALLOWED_HOSTS=yourdomain.com
CORS_ALLOWED_ORIGINS=https://yourdomain.com
```

### Production Checklist
- [ ] Set `DEBUG=0` and configure `ALLOWED_HOSTS`
- [ ] Use strong `SECRET_KEY` and `DB_PASSWORD`
- [ ] Enable TLS/HTTPS via reverse proxy (nginx)
- [ ] Configure bank SMTP for OTP email delivery
- [ ] Set up daily PostgreSQL backups
- [ ] Configure log rotation and monitoring

---

## About this project

This is a portfolio project — a realistic core-banking platform built to practice the hard parts of financial software: a correct double-entry ledger, concurrency-safe and idempotent money operations, OTP/JWT authentication, maker-checker segregation of duties, and an immutable audit trail. It is a demo for learning and demonstration, not a live financial service.

**Author:** Julian Becerra — [github.com/julianbecerra13](https://github.com/julianbecerra13)
