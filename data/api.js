// Thin HTTP client around the FastAPI backend.
//
// Auth: every call forwards the user's Firebase ID token (when present) as
// `Authorization: Bearer <token>`. The browser holds the token in memory;
// EJS-rendered pages pass it through via a request-scoped middleware. If no
// token is present we still try the call — the backend allows unauth in dev
// (FIREBASE_PROJECT_ID empty) and rejects in prod.
//
// Falls back to the static mock dataset when the backend is unreachable so
// the dashboard never goes blank — Node logs the fallback so it's obvious
// when v1 data isn't actually flowing.

const BASE = process.env.BACKEND_URL || 'http://localhost:8000';
const TIMEOUT_MS = 1500;

const mock = require('./mock');

function bearerFrom(req) {
  // Pages can pass through a token by setting req.idToken in middleware;
  // for now we look for a server-side override in env (useful for testing).
  if (req && req.idToken) return `Bearer ${req.idToken}`;
  if (process.env.SERVICE_BEARER) return `Bearer ${process.env.SERVICE_BEARER}`;
  return null;
}

async function tryFetch(req, urlPath) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const headers = { Accept: 'application/json' };
    const auth = bearerFrom(req);
    if (auth) headers.Authorization = auth;

    const res = await fetch(`${BASE}${urlPath}`, { signal: ctrl.signal, headers });
    if (!res.ok) {
      // Don't log response bodies — they could contain echoed tokens / PII.
      throw new Error(`HTTP ${res.status}`);
    }
    return await res.json();
  } catch (e) {
    if (!global.__signalBackendDown) {
      console.warn(`[backend offline → mock] ${urlPath}: ${e.message}`);
      global.__signalBackendDown = Date.now();
    }
    return null;
  } finally {
    clearTimeout(t);
  }
}

async function getSignals(req) {
  const live = await tryFetch(req, '/api/v1/signals');
  return live && live.length ? live : mock.signals;
}

async function getNews(req, limit = 40) {
  const live = await tryFetch(req, `/api/v1/news?limit=${limit}`);
  if (live && live.length) {
    if (live[0]) live[0].featured = true;
    return live;
  }
  return mock.news.slice(0, limit);
}

async function getTicker(req, symbol) {
  const safe = encodeURIComponent(symbol);
  const live = await tryFetch(req, `/api/v1/ticker/${safe}`);
  if (live && live.signal) {
    const fundamentals = await tryFetch(req, `/api/v1/fundamentals/${safe}`);
    return {
      signal: live.signal,
      news: live.news || [],
      history: mock.priceHistory(symbol),
      fundamentals: fundamentals?.fundamentals || mock.fundamentals(symbol),
    };
  }
  const sig = mock.signals.find((s) => s.ticker === symbol) || mock.signals[0];
  return {
    signal: sig,
    news: mock.news.filter((n) => n.tickers.includes(symbol)).concat(mock.news).slice(0, 6),
    history: mock.priceHistory(symbol),
    fundamentals: mock.fundamentals(symbol),
  };
}

async function search(req, q) {
  const live = await tryFetch(req, `/api/v1/search?q=${encodeURIComponent(q)}`);
  if (live) return live;
  return { tickers: [], pages: [] };
}

async function getMlPerformance(req) {
  const live = await tryFetch(req, '/api/v1/ml/performance');
  if (live) return live;
  // Cold-start fallback so the page never crashes.
  return {
    generated_at: null,
    horizons: ['1d', '5d', '21d'].map((h) => ({
      horizon: h,
      model: null,
      resolved: 0,
      pending: 0,
      hit_rate_pct: null,
      high_conf_hit_rate_pct: null,
      mean_predicted_prob: null,
      mean_realized_return_pct: null,
      calibration: [],
    })),
    recent: [],
  };
}

async function getAllTickers(req) {
  // include_inactive=true returns the full universe (active + inactive)
  // so the management UI can render toggles for everything.
  const live = await tryFetch(req, '/api/v1/tickers?include_inactive=true');
  if (live && live.length) return live;
  // Mock fallback derived from the seed list so the UI still functions
  // when the backend is offline.
  return mock.signals.map((s) => ({
    symbol: s.ticker,
    name: s.name,
    sector: s.sector,
    industry: null,
    exchange: 'NASDAQ',
    is_active: ['NVDA', 'AAPL', 'MSFT', 'TSLA', 'GOOGL'].includes(s.ticker),
  }));
}

async function postTickerAction(req, body) {
  // Used by the ticker manager to toggle active state / add new symbols.
  // Returns { ok: true } or { ok: false, status } so the UI can show a toast.
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const headers = { Accept: 'application/json', 'Content-Type': 'application/json' };
    const auth = bearerFrom(req);
    if (auth) headers.Authorization = auth;
    const r = await fetch(`${BASE}${body.path}`, {
      method: body.method || 'POST',
      headers,
      signal: ctrl.signal,
      body: body.json ? JSON.stringify(body.json) : undefined,
    });
    if (!r.ok) return { ok: false, status: r.status };
    return await r.json();
  } catch (e) {
    return { ok: false, status: 0, error: e.message };
  } finally {
    clearTimeout(t);
  }
}

module.exports = {
  getSignals, getNews, getTicker, search, getMlPerformance,
  getAllTickers, postTickerAction, mock,
};
