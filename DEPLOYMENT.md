# Deployment

Signal has **two halves** and they need different homes:

| Half | Tech | Host |
|---|---|---|
| Frontend (SSR pages) | Node 18 + Express + EJS | **Vercel** (or Render / Fly.io) |
| Backend (API + workers) | Python 3.12 + FastAPI + Postgres + Redis | **Railway / Fly.io / Render / a VPS** — not Vercel |

Why not all on Vercel? The backend runs long-lived workers (news ingestion,
classification, fundamentals refresh), needs persistent Postgres and Redis,
and the FastAPI process keeps an HTTP connection pool open to Yahoo / Finnhub
between requests. Serverless wakes up cold for each request, which would
break that. Vercel is great for the Express frontend, though.

---

## Quickstart (local)

```bash
# 1. Fill in keys
cp backend/.env.example backend/.env
# edit backend/.env — paste FINNHUB_API_KEY, ANTHROPIC_API_KEY, FRED_API_KEY

# 2. Backend
cd backend
docker compose up -d postgres redis
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m seed.tickers
docker compose up           # api on :8000, worker in same compose

# 3. Frontend (new terminal)
cd ..
npm install
npm run dev                 # http://localhost:3000
```

---

## Production deploy

### A. Backend → Railway (recommended for v1)

1. Create a new Railway project, add **Postgres** + **Redis** plugins.
2. Push the `backend/` directory as a Railway service. Railway auto-detects
   the `Dockerfile`.
3. Add a second service from the same repo with `Start Command`:
   `python -m app.workers.run`
4. In Railway → Service → Variables, set:

   ```
   APP_ENV=prod
   ANTHROPIC_API_KEY=...
   FINNHUB_API_KEY=...
   FRED_API_KEY=...
   FIREBASE_PROJECT_ID=<your firebase project id>
   ALLOWED_USERS=<comma-separated emails>  # optional private-beta gate
   CORS_ORIGINS=https://signal-app.vercel.app
   ALLOWED_HOSTS=api.signal.app,signal-backend.up.railway.app
   RATE_LIMIT_PER_MINUTE=60
   ```
   `DATABASE_URL` and `REDIS_URL` come from the plugins automatically.

5. Confirm migrations ran (Railway logs should show `alembic upgrade head`
   if you wire it into the Dockerfile entrypoint, or run it manually
   once via `railway run`).

### B. Frontend → Vercel

1. `vercel link` from the repo root.
2. Vercel project settings → Environment Variables:

   ```
   BACKEND_URL=https://signal-backend.up.railway.app
   NODE_ENV=production
   COOKIE_SECRET=<32+ random bytes>
   RATE_LIMIT_PER_MINUTE=120

   # Public Firebase web config — safe to expose (per Firebase docs)
   FIREBASE_WEB_API_KEY=AIza...
   FIREBASE_AUTH_DOMAIN=signal-xxxx.firebaseapp.com
   FIREBASE_PROJECT_ID=signal-xxxx
   FIREBASE_APP_ID=1:1234567890:web:abcdef
   ```

3. `git push` → Vercel rebuilds → done. `vercel.json` handles the
   routing through `server.js`.

### C. DNS

Point `signal.app` → Vercel and `api.signal.app` → Railway. Add the
Vercel domain to `CORS_ORIGINS` and the Railway domain to
`ALLOWED_HOSTS` on the backend.

---

## Firebase Auth setup

1. Console → Authentication → Sign-in method → enable Google (and email/
   password if desired).
2. Console → Project settings → General → **Your apps** → Add a Web app
   → copy the config block. Those values go into the Vercel env
   variables above. **These are public** — that's fine, Firebase web
   config is not a secret.
3. Console → Authentication → Settings → **Authorized domains** → add
   `signal.app` and `signal-app.vercel.app`.
4. Whenever a user signs in, the browser receives an ID token. The
   frontend stores it in memory (NOT localStorage — XSS risk) and
   forwards it on every API call.

The backend never holds a Firebase service-account JSON. Verification
goes against Google's public certs (see `backend/app/security/auth.py`).

---

## Migrations

```bash
docker compose run --rm api alembic upgrade head
```

To create a new revision:

```bash
docker compose run --rm api alembic revision -m "describe change"
# edit migrations/versions/<rev>_*.py
docker compose run --rm api alembic upgrade head
```

---

## Smoke tests post-deploy

```bash
# Backend is alive (public — no auth required)
curl -sf https://api.signal.app/healthz

# Auth is enforced
curl -i https://api.signal.app/api/v1/signals   # expect 401 in prod

# Frontend is alive
curl -sf https://signal.app | head -50

# CSP headers are set
curl -sI https://signal.app | grep -i 'content-security-policy'
```

---

## Cost ceiling

| Thing | Roughly costs | Notes |
|---|---|---|
| Anthropic Claude Haiku 4.5 | $1/M input + $5/M output, ~$5–15/mo at v1 volumes | Prompt caching keeps this low. |
| Finnhub free tier | $0 | 60 req/min — comfortable. |
| FRED | $0 | No usage limits worth worrying about. |
| Railway (Postgres + Redis + 2 services) | $5–15/mo on the starter plan | |
| Vercel | $0 on hobby plan | |
| Firebase Auth | $0 up to 50k MAU | |
