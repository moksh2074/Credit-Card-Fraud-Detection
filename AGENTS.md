# AGENTS.md — Fraud Detection Platform
## Authoritative Instructions for All AntiGravity Agents

---

## PROJECT IDENTITY
Name: Credit Card Fraud Detection Platform
Version: 1.0
Architecture Reference: See /docs/system_design_v2.md

## TECHNOLOGY STACK
- Frontend: Vite + React 18 + Tailwind CSS v3 + Recharts + React Leaflet
- Backend: Python 3.11 + FastAPI + SQLAlchemy (async) + Celery + Redis
- Database: PostgreSQL (IBM Cloud DB)
- ML: scikit-learn RandomForestClassifier + SHAP
- SIEM: Wazuh (log forwarding only — agents do not modify Wazuh internals)
- Storage: IBM Cloud Object Storage (S3-compatible SDK)
- Notifications: IBM Cloud Event Notifications SDK
- Auth: JWT (PyJWT) + Passlib bcrypt

## DATA SOURCE RULE — CRITICAL
The ONLY source of transaction data is the internal Synthetic Transaction Generator.
There is NO external payment gateway. There is NO third-party simulator.
All transaction flows originate from: backend/app/generator/synthetic/

## DIRECTORY RULES
- Never create files outside the structure defined in the project scaffold.
- All FastAPI routes belong in: backend/app/api/routes/
- All React components belong in: frontend/src/components/
- All page-level components belong in: frontend/src/pages/
- Reusable UI atoms go in: frontend/src/components/ui/
- Global styles go in: frontend/src/styles/globals.css ONLY. No inline styles.
- Tailwind custom tokens go in: frontend/tailwind.config.js ONLY.

## NAMING CONVENTIONS
- Python files: snake_case (transaction_service.py)
- React components: PascalCase files and exports (TransactionTable.jsx)
- CSS classes: fd- prefix for custom classes (fd-card, fd-btn-primary)
- API routes: kebab-case paths (/api/v1/transactions/ingest)
- DB table names: snake_case plural (transactions, fraud_alerts, audit_logs)
- Environment variables: SCREAMING_SNAKE_CASE (IBM_COS_API_KEY)

## DESIGN SYSTEM — NON-NEGOTIABLE
Primary color (Color A): #6366F1 (Electric Indigo)
Alert color (Color B): #EF4444 (Crimson Red)
Background base: #0B0F1A (Deep Navy)
Card surface: #111827 (Dark Slate)
Elevated card: #1A2236
Primary text: #F1F5F9
Secondary text: #94A3B8
Font: Inter (primary), JetBrains Mono (IDs/hashes)

All design tokens are defined in tailwind.config.js and globals.css.
Agent B must only read from those files and apply classes — never hardcode hex values in components.

Status colors:
- LOW risk: #10B981 (Emerald)
- MEDIUM risk: #F59E0B (Amber)
- HIGH risk: #F97316 (Orange)
- CRITICAL/FRAUD: #EF4444 (Crimson — Color B)
- APPROVED: #10B981

## SECURITY RULES
- Never hardcode secrets, API keys, or passwords in any file.
- Use os.getenv() for all secrets in Python.
- Use import.meta.env for all secrets in Vite/React.
- Never store plaintext PAN (card numbers). Hash immediately at API boundary.
- JWT access token TTL: 15 minutes. Refresh token TTL: 7 days, single-use.

## CODE QUALITY RULES
- All Python functions must have type hints.
- All API endpoints must have Pydantic request/response schemas.
- Every FastAPI route must have a try/except with proper HTTP exception handling.
- React components must not have prop drilling deeper than 2 levels — use Zustand.
- No TODO comments left in final code. Either implement or remove.

## WHAT AGENTS MUST NOT DO
- Do not modify Wazuh XML files directly. Only generate them as output files.
- Do not create CSS in any file except globals.css and tailwind.config.js.
- Do not install packages without listing them in requirements.txt or package.json.
- Do not create duplicate files. Check if the file exists before creating.
- Do not start a FastAPI server unless Agent C explicitly needs it for testing.