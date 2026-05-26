# Security posture

The goal is simple: **no one — not a stranger, not a packet sniffer, not an
LLM transcript reader — should ever be able to steal the Anthropic, Finnhub,
or Firebase keys out of this project**, and the deployed app should be a
genuinely hostile target for the kinds of attackers who scan small SaaS
sites for low-hanging fruit.

This doc explains exactly what protects what.

---

## 1. Secrets never leave the backend

| Secret | Lives in | Reachable from |
|---|---|---|
| `ANTHROPIC_API_KEY` | `backend/.env` (gitignored) | Python worker process only |
| `FINNHUB_API_KEY` | `backend/.env` (gitignored) | Python worker + API process |
| `FRED_API_KEY` | `backend/.env` (gitignored) | Python worker process |
| Firebase **service account** | NOT USED — we verify ID tokens against Google's public certs. No service-account JSON exists anywhere. | n/a |
| Firebase **web config** | Environment variables, injected into HTML | Public (this is **intentional** — Firebase web config is not a secret) |

**The Node/Express frontend never touches these.** It only proxies through
`data/api.js` to the Python API on `localhost:8000` (dev) or your private
backend URL (prod). The browser bundle has zero credentials.

---

## 2. Don't-commit-it tooling

- `.gitignore` blocks `.env`, `.env.*`, `*.pem`, `*.key`, `service-account*.json`,
  and the standard set of credential filenames.
- `.pre-commit-config.yaml` runs **gitleaks** and **detect-secrets** on
  every `git commit`. If you paste an API key into a file by mistake, the
  commit is blocked.
- `npm run audit:secrets` greps the working tree for things that look
  like keys.

To enable pre-commit:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files   # baseline
```

---

## 3. Logs never leak secrets

`backend/app/security/scrub.py` installs a logging filter on the root
logger. Before any log record hits stdout (and therefore your container
logs / Sentry / aggregator), it gets passed through regex redaction:

- `sk-…` (Anthropic / OpenAI shapes)
- `?token=…` / `&token=…` / `"token": "…"` (Finnhub query params)
- `Bearer …`, `Basic …`, `x-api-key: …`
- `?api_key=…` (FRED)
- `-----BEGIN … PRIVATE KEY-----` blocks
- `eyJ…eyJ…` JWTs
- `postgres://user:password@…`

Both the API process (`app.main`) and the worker process (`app.workers.run`)
call `scrub.install()` at startup, so every code path is covered.

---

## 4. API hardening

The FastAPI app applies, in order:

1. **TrustedHostMiddleware** — rejects requests whose `Host` header
   doesn't match `ALLOWED_HOSTS`. Defeats host-header injection.
2. **CORS** — explicit origin allow-list. Wildcard `*` is refused at
   startup when `APP_ENV=prod`.
3. **SecurityHeadersMiddleware** — CSP (`default-src 'none'`),
   X-Frame-Options, X-Content-Type-Options, Permissions-Policy, HSTS
   (prod only).
4. **SlowAPIMiddleware** — per-IP rate limit (default 60/min, 20/10s
   burst). Configurable via `RATE_LIMIT_PER_MINUTE`/`RATE_LIMIT_BURST`.
5. **GZip** — bandwidth saver.
6. **Auth dependency** — every `/api/v1/*` route runs through
   `current_user` (Firebase ID-token verification). Auth is opt-in via
   `FIREBASE_PROJECT_ID`; production startup refuses to boot without it.
7. **Allow-list** — optional `ALLOWED_USERS` env var pins access to a
   beta cohort while the app is private.

Docs/OpenAPI endpoints (`/docs`, `/redoc`, `/openapi.json`) are
**disabled in prod** so the API surface isn't self-documented to attackers.

---

## 5. Frontend hardening (Express + EJS)

- **helmet** with a strict Content Security Policy. Every inline
  `<script>` / `<style>` tag carries a per-request nonce; anything
  without it is blocked.
- **HSTS** (prod), **X-Frame-Options: DENY**, **Referrer-Policy:
  strict-origin-when-cross-origin**.
- **express-rate-limit** — 120 req/min per IP for pages, 20 req/min for
  the auth proxy.
- **hpp** blocks HTTP-parameter-pollution attacks.
- Body size **capped at 32 KB** (no uploads here).
- Cookies are **signed** (`cookie-parser` with a long random secret).
- **`x-powered-by`** disabled — no framework fingerprint.
- Error handler **strips stack traces** from responses.

---

## 6. Auth model

We use **Firebase Authentication** for sign-in (Google, email, etc).
Firebase issues a JWT ID token in the browser; the frontend forwards it
as `Authorization: Bearer <token>` on every backend call. The backend:

1. Fetches Google's public signing certs (cached for 1h).
2. Verifies the JWT signature + `iss`/`aud`/`exp` claims.
3. Optionally rejects users not in `ALLOWED_USERS`.

We **never** load a Firebase service-account private key (no
`firebase-admin` SDK) — that's one less secret to lose. Token
verification is done with `python-jose` against Google's public certs.

---

## 7. Database & Redis

- Local dev: defaults (`signal:signal`) — fine because Postgres + Redis
  aren't exposed.
- Production (`docker-compose.prod.yml`): credentials come from env
  vars, no port mappings (so they're only reachable on the internal
  Docker network), Redis requires a password.
- SQLAlchemy uses parameterised queries everywhere — no SQL injection
  surface.

---

## 8. Vercel deployment notes

- Frontend (`server.js`) deploys to Vercel as a Node serverless function
  via `vercel.json`. The CSP from helmet plus the static headers in
  `vercel.json` defend in depth.
- The Python backend **cannot** run on Vercel — it needs persistent
  Postgres + Redis + long-running workers. See `DEPLOYMENT.md` for the
  recommended host (Railway / Fly.io / Render / a VPS).
- Set `BACKEND_URL` on the Vercel project to point at your backend's
  HTTPS URL. Vercel will inject it into the Express runtime.

---

## 9. What's still on the to-do list

- WebAuthn / passkeys (Firebase supports it; haven't wired it on the
  client).
- Per-user (not just per-IP) rate-limiting on the API. Add once auth is
  the norm.
- Sentry / OpenTelemetry — log scrubbing already happens, but we should
  validate the integration before shipping logs off-host.
- Dependency-audit CI step (`pip-audit`, `npm audit`).

---

## 10. If you think a key has leaked

1. **Rotate it immediately**. Anthropic / Finnhub / Firebase consoles
   all support one-click rotation.
2. Revoke the old key on the provider side.
3. Update `backend/.env` (or your secrets manager for prod) with the new
   key. Restart `api` + `worker`.
4. Push notification to anyone with shell access that the rotation has
   happened so they pull the latest env.
5. Audit `git log -p` to see what was committed and grep for the
   exposed key in commit messages too.
