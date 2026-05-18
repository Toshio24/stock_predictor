// Thin HTTP client around the FastAPI backend.
// Falls back to the static mock dataset when the backend is unreachable so
// the dashboard never goes blank — but the Node server logs the fallback so
// you can see when v1 data isn't actually flowing.

const BASE = process.env.BACKEND_URL || 'http://localhost:8000';
const TIMEOUT_MS = 1500;

const mock = require('./mock');

async function tryFetch(path) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}${path}`, { signal: ctrl.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    if (!global.__signalBackendDown) {
      console.warn(`[backend offline → mock] ${path}: ${e.message}`);
      global.__signalBackendDown = Date.now();
    }
    return null;
  } finally {
    clearTimeout(t);
  }
}

async function getSignals() {
  const live = await tryFetch('/api/v1/signals');
  return live && live.length ? live : mock.signals;
}

async function getNews(limit = 40) {
  const live = await tryFetch(`/api/v1/news?limit=${limit}`);
  if (live && live.length) {
    if (live[0]) live[0].featured = true;
    return live;
  }
  return mock.news.slice(0, limit);
}

async function getTicker(symbol) {
  const live = await tryFetch(`/api/v1/ticker/${encodeURIComponent(symbol)}`);
  if (live && live.signal) {
    return {
      signal: live.signal,
      news: live.news || [],
      history: mock.priceHistory(symbol),
      fundamentals: mock.fundamentals(symbol),
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

async function search(q) {
  const live = await tryFetch(`/api/v1/search?q=${encodeURIComponent(q)}`);
  if (live) return live;
  return { tickers: [], pages: [] };
}

module.exports = { getSignals, getNews, getTicker, search, mock };
