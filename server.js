const express = require('express');
const path = require('path');
const mock = require('./data/mock');

const app = express();
const PORT = process.env.PORT || 3000;

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(express.static(path.join(__dirname, 'public')));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// shared locals for every render
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
    { href: '/alerts', label: 'Alerts', icon: 'alerts' },
    { href: '/settings', label: 'Settings', icon: 'settings' },
  ];
  res.locals.user = { name: 'Aizen', email: 'aizen@sondrdesigns.com', initials: 'AS' };
  res.locals.marketStatus = mock.marketStatus();
  res.locals.notifications = mock.notifications;
  res.locals.currentPath = req.path;
  next();
});

const render = (view, title, extras = {}) => (req, res) => {
  res.render('layouts/main', {
    view: `pages/${view}`,
    title,
    page: view,
    ...extras,
  });
};

// dashboard
app.get('/', (req, res) => {
  res.render('layouts/main', {
    view: 'pages/dashboard',
    title: 'Dashboard',
    page: 'dashboard',
    indices: mock.indices,
    signals: mock.signals.slice(0, 6),
    news: mock.news.slice(0, 8),
    watchlist: mock.watchlist,
    sectors: mock.sectors,
    accuracy: mock.accuracy,
  });
});

// signals explorer
app.get('/signals', (req, res) => {
  res.render('layouts/main', {
    view: 'pages/signals',
    title: 'Signals',
    page: 'signals',
    signals: mock.signals,
  });
});

// ticker detail
app.get('/ticker/:symbol', (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  const signal = mock.signals.find((s) => s.ticker === symbol) || mock.signals[0];
  res.render('layouts/main', {
    view: 'pages/ticker',
    title: symbol,
    page: 'ticker',
    symbol,
    signal,
    news: mock.news.filter((n) => n.tickers.includes(symbol)).concat(mock.news).slice(0, 6),
    history: mock.priceHistory(symbol),
    fundamentals: mock.fundamentals(symbol),
  });
});

// news feed
app.get('/news', (req, res) => {
  res.render('layouts/main', {
    view: 'pages/news',
    title: 'News',
    page: 'news',
    news: mock.news,
    breaking: mock.news[0],
  });
});

// stub pages
app.get('/watchlist', render('watchlist', 'Watchlist', { watchlist: mock.watchlist }));
app.get('/screener', render('screener', 'Screener'));
app.get('/portfolio', render('portfolio', 'Portfolio'));
app.get('/compare', render('compare', 'Compare'));
app.get('/backtest', render('backtest', 'Backtest'));
app.get('/alerts', render('alerts', 'Alerts'));
app.get('/settings', render('settings', 'Settings'));

// auth (non-glassmorphic)
const renderAuth = (view, title) => (req, res) => {
  res.render('layouts/auth', { view: `pages/${view}`, title, page: view });
};
app.get('/login', renderAuth('login', 'Log in'));
app.get('/signup', renderAuth('signup', 'Sign up'));
app.get('/forgot-password', renderAuth('forgot-password', 'Reset password'));
app.get('/onboarding', renderAuth('onboarding', 'Welcome'));

// mock auth endpoints (localStorage handles state client-side)
app.post('/api/auth/login', (req, res) => res.json({ ok: true, user: { name: 'Aizen', email: req.body.email } }));
app.post('/api/auth/signup', (req, res) => res.json({ ok: true, user: { name: req.body.name || 'New User', email: req.body.email } }));

// search
app.get('/api/search', (req, res) => {
  const q = (req.query.q || '').toLowerCase().trim();
  if (!q) return res.json({ tickers: [], pages: [] });
  const tickers = mock.signals
    .filter((s) => s.ticker.toLowerCase().includes(q) || s.name.toLowerCase().includes(q))
    .slice(0, 5)
    .map((s) => ({ ticker: s.ticker, name: s.name, signal: s.signal, score: s.score }));
  const pages = res.locals.nav.filter((n) => n.label.toLowerCase().includes(q)).slice(0, 4);
  res.json({ tickers, pages });
});

// 404
app.use((req, res) => {
  res.status(404).render('layouts/main', {
    view: 'pages/404',
    title: 'Not found',
    page: '404',
  });
});

app.listen(PORT, () => {
  console.log(`Signal running → http://localhost:${PORT}`);
});
