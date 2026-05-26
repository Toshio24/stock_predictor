// Signal — Node/Express SSR frontend.
//
// Security posture:
//   - helmet sets CSP, HSTS, X-Frame, no-sniff, etc.
//   - express-rate-limit caps per-IP request rate (defence against scrapers).
//   - hpp blocks HTTP parameter pollution.
//   - cookie-parser is configured with signed cookies only.
//   - Body size capped at 32kb (no file uploads here).
//   - Trust proxy is set in prod so X-Forwarded-* is respected (Vercel).
//   - No secret ever leaves the backend — the frontend only proxies through
//     data/api.js, which talks to the Python API. There is no path in this
//     server that has direct access to the Anthropic/Finnhub keys.

const express = require('express');
const helmet = require('helmet');
const compression = require('compression');
const rateLimit = require('express-rate-limit');
const cookieParser = require('cookie-parser');
const hpp = require('hpp');
const crypto = require('crypto');
const path = require('path');

const mock = require('./data/mock');
const api = require('./data/api');

const app = express();
const PORT = process.env.PORT || 3000;
const IS_PROD = process.env.NODE_ENV === 'production';

// Behind Vercel / a reverse proxy → trust the X-Forwarded-* headers so
// req.ip and req.protocol reflect the real client. Only do this when
// actually deployed — locally we want to refuse spoofed headers.
if (IS_PROD) app.set('trust proxy', 1);

// Don't leak the framework.
app.disable('x-powered-by');

// ---------------------------------------------------------------------------
// helmet — security headers. The CSP is strict but allows:
//   • Tailwind CDN (we'll move to a local build before launch)
//   • Inline event handlers in our existing EJS (allowed via nonce)
// Every <script>/<style> tag in the templates must include the
// `nonce=<%= cspNonce %>` attribute. Failing to do so will block the asset
// — that's intentional, it forces the developer to think about it.
// ---------------------------------------------------------------------------
app.use((req, res, next) => {
  res.locals.cspNonce = crypto.randomBytes(16).toString('base64');
  next();
});

app.use(
  helmet({
    contentSecurityPolicy: {
      useDefaults: true,
      directives: {
        defaultSrc: ["'self'"],
        scriptSrc: [
          "'self'",
          (req, res) => `'nonce-${res.locals.cspNonce}'`,
          'https://cdn.tailwindcss.com',
          'https://www.gstatic.com', // Firebase JS SDK
          'https://www.googleapis.com',
        ],
        styleSrc: [
          "'self'",
          "'unsafe-inline'", // Tailwind utility classes generate inline styles
          'https://cdn.tailwindcss.com',
          'https://fonts.googleapis.com',
        ],
        fontSrc: ["'self'", 'https://fonts.gstatic.com', 'data:'],
        imgSrc: ["'self'", 'data:', 'https:'],
        connectSrc: [
          "'self'",
          process.env.BACKEND_URL || 'http://localhost:8000',
          'https://*.googleapis.com',     // Firebase auth
          'https://securetoken.googleapis.com',
          'https://identitytoolkit.googleapis.com',
        ],
        frameAncestors: ["'none'"],
        objectSrc: ["'none'"],
        baseUri: ["'self'"],
        formAction: ["'self'"],
        upgradeInsecureRequests: IS_PROD ? [] : null,
      },
    },
    crossOriginEmbedderPolicy: false, // Firebase popups need this off
    referrerPolicy: { policy: 'strict-origin-when-cross-origin' },
    hsts: IS_PROD ? { maxAge: 31536000, includeSubDomains: true, preload: true } : false,
  }),
);

// ---------------------------------------------------------------------------
// Other middleware
// ---------------------------------------------------------------------------
app.use(compression());
app.use(hpp());
app.use(express.json({ limit: '32kb' }));
app.use(express.urlencoded({ extended: true, limit: '32kb' }));
app.use(cookieParser(process.env.COOKIE_SECRET || crypto.randomBytes(32).toString('hex')));

// Per-IP rate limiter. Page renders and JSON proxies share the same budget.
// 120 req/min is generous for human use, painful for a scraper.
const limiter = rateLimit({
  windowMs: 60 * 1000,
  max: Number(process.env.RATE_LIMIT_PER_MINUTE || 120),
  standardHeaders: 'draft-7',
  legacyHeaders: false,
  message: { error: 'Too many requests' },
});
app.use(limiter);

// Tighter limit on the auth proxy — if Firebase is enabled we don't want
// brute force on the verify endpoint.
const authLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 20,
  standardHeaders: 'draft-7',
  legacyHeaders: false,
});

// View engine
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(express.static(path.join(__dirname, 'public'), {
  maxAge: IS_PROD ? '7d' : 0,
  etag: true,
}));

// ---------------------------------------------------------------------------
// Locals applied to every view
// ---------------------------------------------------------------------------
app.use((req, res, next) => {
  res.locals.nav = [
    { href: '/', label: 'Dashboard', icon: 'dashboard' },
    { href: '/signals', label: 'Signals', icon: 'signals' },
    { href: '/news', label: 'News', icon: 'news' },
    { href: '/watchlist', label: 'Watchlist', icon: 'watchlist' },
    { href: '/screener', label: 'Screener', icon: 'screener' },
    { href: '/portfolio', label: 'Portfolio', icon: 'portfolio' },
    { href: '/compare', label: 'Compare', icon: 'compare' },
    { href: '/backtest', label: 'Backtest', icon: 'backtest' },
    { href: '/ml', label: 'ML Data', icon: 'brain' },
    { href: '/alerts', label: 'Alerts', icon: 'alerts' },
    { href: '/settings', label: 'Settings', icon: 'settings' },
  ];
  // Real user identity will come from Firebase ID-token claims once auth
  // is wired up. For now we render a placeholder so views don't crash.
  res.locals.user = { name: 'Toshi Nagai', email: 'test@gmail.com', initials: 'TN' };
  res.locals.marketStatus = mock.marketStatus();
  res.locals.notifications = mock.notifications;
  res.locals.currentPath = req.path;
  res.locals.firebaseConfig = {
    // Public Firebase config (NOT a secret — it's safe to expose in HTML).
    // Wire these in when you set up your Firebase project; until then auth
    // is disabled and we fall through to the dev experience.
    apiKey: process.env.FIREBASE_WEB_API_KEY || '',
    authDomain: process.env.FIREBASE_AUTH_DOMAIN || '',
    projectId: process.env.FIREBASE_PROJECT_ID || '',
    appId: process.env.FIREBASE_APP_ID || '',
  };
  next();
});

const render = (view, title, extras = {}) => (req, res) => {
  res.render('layouts/main', { view: `pages/${view}`, title, page: view, ...extras });
};

// ---------------------------------------------------------------------------
// Pages
// ---------------------------------------------------------------------------
app.get('/', async (req, res) => {
  const [signals, news] = await Promise.all([api.getSignals(req), api.getNews(req, 20)]);
  res.render('layouts/main', {
    view: 'pages/dashboard',
    title: 'Dashboard',
    page: 'dashboard',
    indices: mock.indices,
    signals: signals.slice(0, 6),
    news: news.slice(0, 8),
    watchlist: mock.watchlist,
    sectors: mock.sectors,
    accuracy: mock.accuracy,
  });
});

app.get('/signals', async (req, res) => {
  const signals = await api.getSignals(req);
  res.render('layouts/main', { view: 'pages/signals', title: 'Signals', page: 'signals', signals });
});

app.get('/ticker/:symbol', async (req, res) => {
  const symbol = String(req.params.symbol || '').toUpperCase().replace(/[^A-Z0-9.\-]/g, '').slice(0, 10);
  if (!symbol) return res.redirect('/signals');
  const data = await api.getTicker(req, symbol);
  res.render('layouts/main', {
    view: 'pages/ticker',
    title: symbol,
    page: 'ticker',
    symbol,
    signal: data.signal,
    news: data.news,
    history: data.history,
    fundamentals: data.fundamentals,
  });
});

app.get('/news', async (req, res) => {
  const news = await api.getNews(req, 40);
  res.render('layouts/main', { view: 'pages/news', title: 'News', page: 'news', news, breaking: news[0] || mock.news[0] });
});

app.get('/watchlist', async (req, res) => {
  const tickers = await api.getAllTickers(req);
  res.render('layouts/main', {
    view: 'pages/watchlist',
    title: 'Watchlist',
    page: 'watchlist',
    tickers,
  });
});

// Ticker-management proxy. The frontend toggles is_active on the backend
// so the workers stop spending API credits on tickers the user opted out of.
app.post('/api/tickers/:symbol/:action', async (req, res) => {
  const symbol = String(req.params.symbol || '').toUpperCase().replace(/[^A-Z0-9.\-]/g, '').slice(0, 10);
  const action = String(req.params.action || '');
  if (!symbol) return res.status(400).json({ ok: false });
  if (!['activate', 'deactivate'].includes(action)) return res.status(400).json({ ok: false });
  const result = await api.postTickerAction(req, { path: `/api/v1/tickers/${encodeURIComponent(symbol)}/${action}` });
  if (!result || result.ok === false) {
    return res.status(result && result.status ? result.status : 503).json({ ok: false, error: 'backend unreachable' });
  }
  res.json({ ok: true, symbol, is_active: action === 'activate' });
});

app.post('/api/tickers', async (req, res) => {
  const body = req.body || {};
  const payload = {
    symbol: String(body.symbol || '').toUpperCase().replace(/[^A-Z0-9.\-]/g, '').slice(0, 10),
    name: String(body.name || '').trim().slice(0, 200),
    sector: body.sector ? String(body.sector).slice(0, 100) : undefined,
    industry: body.industry ? String(body.industry).slice(0, 100) : undefined,
    exchange: body.exchange ? String(body.exchange).slice(0, 20) : undefined,
  };
  if (!payload.symbol || !payload.name) {
    return res.status(400).json({ ok: false, error: 'symbol and name required' });
  }
  const result = await api.postTickerAction(req, {
    path: '/api/v1/tickers',
    json: payload,
  });
  if (!result || result.ok === false) {
    return res.status(result && result.status ? result.status : 503).json({ ok: false, error: 'backend unreachable' });
  }
  res.json({ ok: true, ...payload });
});
app.get('/screener', render('screener', 'Screener'));
app.get('/portfolio', render('portfolio', 'Portfolio'));
app.get('/compare', render('compare', 'Compare'));
app.get('/backtest', render('backtest', 'Backtest'));
app.get('/ml', async (req, res) => {
  const perf = await api.getMlPerformance(req);
  res.render('layouts/main', {
    view: 'pages/ml',
    title: 'ML Data',
    page: 'ml',
    perf,
  });
});
app.get('/alerts', render('alerts', 'Alerts'));
app.get('/settings', render('settings', 'Settings'));

const renderAuth = (view, title) => (req, res) => {
  res.render('layouts/auth', { view: `pages/${view}`, title, page: view });
};
app.get('/login', renderAuth('login', 'Log in'));
app.get('/signup', renderAuth('signup', 'Sign up'));
app.get('/forgot-password', renderAuth('forgot-password', 'Reset password'));
app.get('/onboarding', renderAuth('onboarding', 'Welcome'));

// ---------------------------------------------------------------------------
// Auth: this is a *thin shim* in front of Firebase.
// Real authentication happens in the browser (Firebase JS SDK). The frontend
// stores the resulting ID token and sends it on every request to /api/* —
// the backend verifies it. These Express endpoints exist only as a fallback
// for the legacy forms; they never issue session tokens themselves.
// ---------------------------------------------------------------------------
app.post('/api/auth/login', authLimiter, (req, res) => {
  const email = String(req.body?.email || '').trim().slice(0, 200);
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return res.status(400).json({ error: 'invalid email' });
  res.json({ ok: true, message: 'Use Firebase client SDK for auth in production.' });
});
app.post('/api/auth/signup', authLimiter, (req, res) => {
  const email = String(req.body?.email || '').trim().slice(0, 200);
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return res.status(400).json({ error: 'invalid email' });
  res.json({ ok: true, message: 'Use Firebase client SDK for auth in production.' });
});

// Search proxy — already validates query length backend-side; we cap here too.
app.get('/api/search', async (req, res) => {
  const q = String(req.query.q || '').trim().slice(0, 40);
  if (!q) return res.json({ tickers: [], pages: [] });
  const live = await api.search(req, q);
  const pages = res.locals.nav
    .filter((n) => n.label.toLowerCase().includes(q.toLowerCase()))
    .slice(0, 4);
  res.json({ tickers: live.tickers || [], pages });
});

// ---------------------------------------------------------------------------
// 404
// ---------------------------------------------------------------------------
app.use((req, res) => {
  res.status(404).render('layouts/main', {
    view: 'pages/404',
    title: 'Not found',
    page: '404',
  });
});

// Don't leak stack traces.
app.use((err, req, res, next) => {
  console.error('[server]', err.message);
  if (res.headersSent) return next(err);
  res.status(500).json({ error: 'Internal server error' });
});

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`Signal running → http://localhost:${PORT}`);
    console.log(`Backend → ${process.env.BACKEND_URL || 'http://localhost:8000'} (falls back to mock if offline)`);
  });
}

module.exports = app;
