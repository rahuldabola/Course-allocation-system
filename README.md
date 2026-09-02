# 🎓 AI-Powered Student Course Allocation System

[![CI](https://github.com/rahuldabola/Course-allocation-system/actions/workflows/ci.yml/badge.svg)](https://github.com/rahuldabola/Course-allocation-system/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A full-stack system that allocates university course seats by **merit and
reservation rules**, with a dashboard for analytics and an **AI assistant**
that answers questions about the allocation in plain English (text-to-SQL via
a local LLM).

> Stack: **Next.js + Tailwind** · **FastAPI** · **PostgreSQL** · **Alembic** · **Ollama (local LLM)**

---

## ✨ Features

- Normalized (3NF) PostgreSQL schema, versioned with **Alembic migrations**.
- REST APIs for student registration, course management, and allocation —
  write endpoints and the AI assistant are gated by an **API key**.
- Merit + reservation **allocation engine** (unit-tested, pure-function core).
- Dashboard: allocated students, available seats, course statistics, category-wise allocation, rejection rates.
- AI Assistant answering the required report questions — and arbitrary ones — by
  generating safe read-only SQL.
- CI on every push/PR: backend lint + tests + migration smoke test, frontend lint + build.

---

## 🚀 Quick start (Docker — recommended)

```bash
docker compose up --build
# one-time: pull a model for the AI assistant
docker compose exec ollama ollama pull llama3.1
# seed sample data (5 courses, 50 students)
docker compose exec backend python -m app.seed
```

- Frontend → http://localhost:3000
- API docs (Swagger) → http://localhost:8000/docs

The backend container runs `alembic upgrade head` automatically before it
starts. Both services share one API key, taken from the `API_KEY` env var
(defaults to `changeme-dev-key` — set a real one via `API_KEY=... docker
compose up` for anything beyond local testing).

> The AI assistant works **without** Ollama too: it falls back to built-in
> report queries for the four required questions.

---

## 🛠️ Local development (without Docker)

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt        # adds pytest + ruff to requirements.txt
cp .env.example .env                       # point DATABASE_URL at a running Postgres, set API_KEY
alembic upgrade head                       # create the schema
python -m app.seed                         # sample courses + students
uvicorn app.main:app --reload              # http://localhost:8000
pytest -q                                  # 29 tests: allocation engine, API, AI-assistant SQL safety
ruff check .                               # lint
```

**Frontend**
```bash
cd frontend
npm install
cp .env.local.example .env.local           # NEXT_PUBLIC_API_URL + NEXT_PUBLIC_API_KEY
npm run dev                                # http://localhost:3000
npm run lint && npm run build              # what CI runs
```

---

## 🔐 Authentication

`POST`/`PUT`/`DELETE` on `/students` and `/courses`, `POST /allocation/run`,
and `POST /assistant/query` require a header `X-API-Key` matching the
backend's `API_KEY` setting, checked with a constant-time comparison
([`backend/app/auth.py`](backend/app/auth.py)). `GET` endpoints (the
dashboard, listings) stay open. If `API_KEY` is left unset, auth is disabled
entirely — convenient for local dev, not recommended for anything shared.

This is deliberately a single shared secret, not a user/role system — there
are no accounts. It stops casual/automated abuse of write and LLM-backed
endpoints; it is not a substitute for real authN/authZ in a multi-tenant
deployment.

---

## 🗄️ Database schema (3NF)

```
categories(id, code, name)
students(id, roll_no, name, marks, category_id→categories, application_date)
courses(id, name, total_seats)
course_quotas(id, course_id→courses, category_id→categories, reserved_seats)   UNIQUE(course_id, category_id)
preferences(id, student_id→students, course_id→courses, priority)              UNIQUE(student_id, priority), UNIQUE(student_id, course_id)
allocations(id, student_id→students UNIQUE, course_id→courses, seat_type, preference_rank, allocated_at)
```

`open_seats(course) = total_seats − Σ reserved_seats`. The `UNIQUE` constraint on
`allocations.student_id` enforces **one course per student** at the schema level.

Schema changes go through Alembic ([`backend/migrations`](backend/migrations)) —
`alembic revision --autogenerate -m "..."` then `alembic upgrade head`. The
app no longer calls `create_all()` at startup; it only seeds base categories.

---

## 🧮 Allocation algorithm

Implemented in [`backend/app/allocation.py`](backend/app/allocation.py) as a pure,
unit-tested function.

1. **Merit order** — students sorted by `marks DESC`, ties broken by earlier
   `application_date`.
2. Walk students in that order; for each, try preferences **1 → 2 → 3**:
   - A **General** student can take only an **open** seat.
   - A **reserved** (OBC/SC/ST) student takes an **open** seat if available
     (earned on merit), otherwise a **reserved** seat of their own category.
   - The first preference with an available seat wins; the student is then done.
3. A student matching none of their preferences remains **unallocated**.

This treats reserved seats as a **floor guarantee**: high-merit reserved students
consume open seats, leaving reserved seats for lower-merit peers of the same
category. `POST /allocation/run` is **idempotent** — it clears and recomputes.

**Worked example** — course with `total=2, SC reserved=1` (so 1 open + 1 SC):
- General@95 → open seat
- SC@60 → SC reserved seat ✅ (floor honored)

If instead SC@99 and SC@70 apply: SC@99 → open seat, SC@70 → SC reserved seat.

---

## 🔌 API overview

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/students` | 🔑 | Register a student + up to 3 preferences |
| GET | `/students` | — | List students (by marks) |
| DELETE | `/students/{id}` | 🔑 | Remove a student |
| POST | `/courses` | 🔑 | Create a course with category quotas |
| GET | `/courses` | — | List courses (with open/reserved seats) |
| PUT | `/courses/{id}` | 🔑 | Update course / quotas |
| POST | `/allocation/run` | 🔑 | Run (idempotent) allocation |
| GET | `/allocation` | — | List current allocations |
| GET | `/dashboard/stats` | — | Aggregated dashboard statistics |
| POST | `/assistant/query` | 🔑 | Ask the AI assistant a question |

🔑 = requires `X-API-Key` when `API_KEY` is set. Full interactive docs at `/docs`.

---

## 🤖 AI Assistant (text-to-SQL)

`POST /assistant/query` sends the schema + question to the local LLM, which
returns a query. Safety: only a **single read-only `SELECT`** is allowed
(keyword blocklist + single-statement check), executed in a **read-only
transaction with a 5s statement timeout**. Results are summarized back in
natural language. If the LLM is unreachable, built-in queries answer the four
required questions:

- How many students were allocated to each course?
- Which students did not receive their first preference?
- Which course had the highest rejection rate?
- Category-wise allocation summary.

---

## ☁️ Deployment (optional)

- **Frontend** → Vercel (set `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_API_KEY`).
- **Backend** → Render / Fly.io / Railway (set `DATABASE_URL`, `OLLAMA_URL`, `API_KEY`;
  the Docker image runs `alembic upgrade head` on boot).
- **DB** → managed Postgres (Neon / Supabase / RDS).

---

## 🧪 Tests & CI

```bash
cd backend && pytest -q     # 29 tests, SQLite-backed, no Postgres required
```

- `tests/test_allocation.py` — allocation engine (pure function, no DB).
- `tests/test_api.py` — request validation, the allocation endpoint end-to-end,
  dashboard aggregation, API-key enforcement.
- `tests/test_ai_assistant_safety.py` — the SQL safety gate rejects writes/multi-statements,
  and the fallback library covers the four required report questions.

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push/PR: backend
`ruff check` + `pytest` + an Alembic upgrade/downgrade smoke test, and frontend
`next lint` + `next build`.

---

## ⚠️ Known limitations

- Auth is a single shared API key (see [Authentication](#-authentication)), not
  per-user accounts or roles.
- No rate limiting on `/assistant/query`, which can call an LLM — fine for a
  demo/single-team deployment, not for a public endpoint.
- SQLite is used only in tests, for speed; Postgres-specific behavior (e.g.
  `SET TRANSACTION READ ONLY` in the AI assistant) is exercised at runtime,
  not in the test suite.

---

## License

MIT — see [LICENSE](LICENSE).
