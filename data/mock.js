// Deterministic mock data for the Signal platform.
// Everything below is purely illustrative — no real prices, no live feeds.

const seeded = (seed) => {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
};

const sparkline = (seed, points = 24, base = 100, vol = 0.04) => {
  const rand = seeded(seed);
  const out = [];
  let v = base;
  for (let i = 0; i < points; i++) {
    v = v * (1 + (rand() - 0.5) * vol);
    out.push(Number(v.toFixed(2)));
  }
  return out;
};

const indices = [
  { name: 'S&P 500', symbol: 'SPX', price: 5872.34, change: 0.62, spark: sparkline(11, 28, 5800) },
  { name: 'Nasdaq 100', symbol: 'NDX', price: 20431.18, change: 1.04, spark: sparkline(22, 28, 20200) },
  { name: 'Dow Jones', symbol: 'DJI', price: 43219.77, change: -0.21, spark: sparkline(33, 28, 43300, 0.02) },
  { name: 'Russell 2000', symbol: 'RUT', price: 2358.91, change: 0.88, spark: sparkline(44, 28, 2330) },
  { name: 'VIX', symbol: 'VIX', price: 14.27, change: -3.42, spark: sparkline(55, 28, 15, 0.08) },
  { name: 'BTC / USD', symbol: 'BTCUSD', price: 96284.55, change: 2.14, spark: sparkline(66, 28, 95000, 0.05) },
  { name: 'ETH / USD', symbol: 'ETHUSD', price: 3412.88, change: 1.62, spark: sparkline(77, 28, 3360, 0.05) },
  { name: '10Y Treasury', symbol: 'TNX', price: 4.31, change: -0.45, spark: sparkline(88, 28, 4.3, 0.02) },
];

const signalSeed = [
  ['NVDA', 'NVIDIA Corp', 'Semiconductors', 'bullish', 142.31, 2.84, 92],
  ['AAPL', 'Apple Inc', 'Consumer Electronics', 'bullish', 232.14, 0.91, 81],
  ['MSFT', 'Microsoft Corp', 'Software', 'bullish', 421.07, 1.32, 88],
  ['TSLA', 'Tesla Inc', 'EV & Mobility', 'bearish', 248.62, -3.14, 74],
  ['META', 'Meta Platforms', 'Social & Ads', 'bullish', 612.88, 1.87, 79],
  ['AMZN', 'Amazon.com Inc', 'E-commerce & Cloud', 'bullish', 224.41, 0.62, 76],
  ['GOOGL', 'Alphabet Inc', 'Search & AI', 'bullish', 192.55, 1.21, 83],
  ['AMD', 'Advanced Micro Devices', 'Semiconductors', 'bearish', 134.22, -2.18, 68],
  ['NFLX', 'Netflix Inc', 'Streaming', 'bullish', 891.04, 0.42, 71],
  ['JPM', 'JPMorgan Chase', 'Banks', 'neutral', 248.91, 0.18, 55],
  ['XOM', 'Exxon Mobil', 'Energy', 'bearish', 109.42, -1.74, 64],
  ['BA', 'Boeing Co', 'Aerospace', 'bearish', 152.18, -2.42, 71],
  ['DIS', 'Walt Disney Co', 'Media', 'bullish', 114.27, 1.04, 67],
  ['UBER', 'Uber Technologies', 'Mobility', 'bullish', 76.41, 2.18, 80],
  ['SHOP', 'Shopify Inc', 'E-commerce', 'bullish', 118.32, 3.41, 85],
  ['COIN', 'Coinbase Global', 'Crypto', 'bullish', 312.55, 4.62, 89],
  ['PLTR', 'Palantir Tech', 'Data & AI', 'bullish', 78.14, 2.91, 87],
  ['INTC', 'Intel Corp', 'Semiconductors', 'bearish', 22.41, -1.84, 62],
  ['F', 'Ford Motor', 'Autos', 'bearish', 10.84, -0.92, 58],
  ['SOFI', 'SoFi Technologies', 'Fintech', 'bullish', 18.32, 3.18, 78],
  ['CRWD', 'CrowdStrike Holdings', 'Cybersecurity', 'bullish', 372.41, 1.62, 82],
  ['ABNB', 'Airbnb Inc', 'Travel', 'neutral', 142.18, 0.32, 53],
];

const signals = signalSeed.map(([ticker, name, sector, signal, price, change, score], i) => ({
  ticker,
  name,
  sector,
  signal,
  price,
  change,
  score,
  confidence: Math.min(99, score + Math.floor((i % 5) * 2)),
  spark: sparkline(ticker.charCodeAt(0) * 7 + i, 28, price, 0.03),
  rationale:
    signal === 'bullish'
      ? 'Momentum + earnings revision tailwinds; technicals confirm trend continuation.'
      : signal === 'bearish'
      ? 'Deteriorating breadth and negative options flow; resistance held on retest.'
      : 'Mixed signals across timeframes — model expressing low conviction.',
  updatedAt: `${(i % 23) + 1}m ago`,
}));

const newsSeed = [
  ['Fed minutes signal patience as inflation cools to 2.4% YoY', 'Bloomberg', 'Macro', 'neutral', ['SPX', 'NDX']],
  ['NVIDIA beats again — Q4 revenue $42.1B, data-center guide raised', 'Reuters', 'Earnings', 'bullish', ['NVDA']],
  ['Apple unveils on-device foundation model for next iOS release', 'The Verge', 'Tech', 'bullish', ['AAPL']],
  ['Tesla recalls 1.2M vehicles over autopark firmware defect', 'WSJ', 'Autos', 'bearish', ['TSLA']],
  ['Microsoft and OpenAI expand Azure compute pact through 2030', 'CNBC', 'Tech', 'bullish', ['MSFT']],
  ['Coinbase clears final EU MiCA license, expands to 27 markets', 'CoinDesk', 'Crypto', 'bullish', ['COIN', 'BTCUSD']],
  ['Boeing 737 production halted after second QA escape in a month', 'FT', 'Industrials', 'bearish', ['BA']],
  ['Meta opens Llama 4 weights to commercial partners under new terms', 'TechCrunch', 'AI', 'bullish', ['META']],
  ['Amazon launches grocery same-day for Prime members in 14 new metros', 'Bloomberg', 'Retail', 'bullish', ['AMZN']],
  ['Oil slides 2.4% as OPEC+ telegraphs a softer cut in December', 'Reuters', 'Energy', 'bearish', ['XOM']],
  ['Palantir lands $480M DoD contract for AIP rollout across CENTCOM', 'WSJ', 'Defense', 'bullish', ['PLTR']],
  ['Netflix ad tier crosses 90M MAU, beating internal Q3 target', 'The Verge', 'Streaming', 'bullish', ['NFLX']],
  ['Shopify ships native AI agents for merchant ops, GMV +21% QoQ', 'Bloomberg', 'E-commerce', 'bullish', ['SHOP']],
  ['Disney+ password sharing crackdown adds 4.2M subs in first quarter', 'CNBC', 'Media', 'bullish', ['DIS']],
  ['Intel 18A yields disappoint analysts; Lip-Bu Tan defends roadmap', 'Reuters', 'Semis', 'bearish', ['INTC']],
  ['Uber Eats integrates with Instacart in surprise grocery alliance', 'TechCrunch', 'Mobility', 'bullish', ['UBER']],
  ['SoFi membership crosses 11M; deposit base hits all-time high', 'Bloomberg', 'Fintech', 'bullish', ['SOFI']],
  ['CrowdStrike post-mortem cites kernel driver regression for July outage', 'WIRED', 'Cyber', 'neutral', ['CRWD']],
  ['Ford pushes EV truck rollout to 2027, takes $1.9B charge', 'WSJ', 'Autos', 'bearish', ['F']],
  ['Airbnb cracks down on party listings ahead of summer season', 'Reuters', 'Travel', 'neutral', ['ABNB']],
  ['Bitcoin reclaims $96K as spot ETFs log 12 straight days of inflows', 'CoinDesk', 'Crypto', 'bullish', ['BTCUSD']],
  ['Goldman lifts S&P 500 year-end target to 6,200 on earnings revisions', 'Bloomberg', 'Macro', 'bullish', ['SPX']],
];

const news = newsSeed.map(([headline, source, category, sentiment, tickers], i) => ({
  id: i + 1,
  headline,
  source,
  category,
  sentiment,
  tickers,
  summary:
    'Editorial summary — model-generated abstract surfaces key facts, market reaction, and probable second-order effects.',
  timeAgo: `${(i % 11) + 1}h ago`,
  featured: i < 2,
}));

const watchlist = [
  { ticker: 'NVDA', name: 'NVIDIA Corp', price: 142.31, change: 2.84, signal: 'bullish', score: 92 },
  { ticker: 'AAPL', name: 'Apple Inc', price: 232.14, change: 0.91, signal: 'bullish', score: 81 },
  { ticker: 'TSLA', name: 'Tesla Inc', price: 248.62, change: -3.14, signal: 'bearish', score: 74 },
  { ticker: 'COIN', name: 'Coinbase Global', price: 312.55, change: 4.62, signal: 'bullish', score: 89 },
  { ticker: 'PLTR', name: 'Palantir Tech', price: 78.14, change: 2.91, signal: 'bullish', score: 87 },
  { ticker: 'BA', name: 'Boeing Co', price: 152.18, change: -2.42, signal: 'bearish', score: 71 },
];

const sectors = [
  { name: 'Technology', change: 1.42, weight: 28 },
  { name: 'Communication', change: 0.92, weight: 9 },
  { name: 'Consumer Disc.', change: 0.61, weight: 11 },
  { name: 'Healthcare', change: -0.18, weight: 12 },
  { name: 'Financials', change: 0.31, weight: 14 },
  { name: 'Industrials', change: -0.42, weight: 8 },
  { name: 'Energy', change: -1.71, weight: 4 },
  { name: 'Utilities', change: 0.08, weight: 3 },
  { name: 'Materials', change: -0.21, weight: 2 },
  { name: 'Real Estate', change: 0.51, weight: 3 },
  { name: 'Staples', change: 0.18, weight: 6 },
];

const notifications = [
  { id: 1, type: 'signal', title: 'New bullish signal: NVDA', body: 'Score crossed 90 — high-conviction long.', timeAgo: '2m', read: false },
  { id: 2, type: 'price', title: 'AAPL hit your price target', body: 'Crossed $230 — adjust your alert?', timeAgo: '14m', read: false },
  { id: 3, type: 'news', title: 'Breaking: Fed minutes', body: 'Sentiment leaning neutral-dovish.', timeAgo: '38m', read: false },
  { id: 4, type: 'system', title: 'Weekly digest ready', body: '12 new signals, 4 closed +6.2%.', timeAgo: '3h', read: true },
  { id: 5, type: 'price', title: 'TSLA below support', body: 'Pierced $250 floor on heavy volume.', timeAgo: '5h', read: true },
];

const accuracy = {
  overall: 78,
  bullish: 82,
  bearish: 71,
  neutral: 64,
  trailing30: [72, 74, 73, 76, 78, 79, 77, 80, 78, 81, 82, 79, 78],
};

const marketStatus = () => {
  const now = new Date();
  const h = now.getUTCHours();
  // NYSE rough hours in UTC: 14:30 - 21:00
  const open = h >= 14 && h < 21;
  return { open, label: open ? 'Markets open' : 'Markets closed', next: open ? 'Close in ' + (21 - h) + 'h' : 'Opens in ' + ((14 - h + 24) % 24) + 'h' };
};

const priceHistory = (symbol) => {
  const seed = symbol.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  return sparkline(seed, 90, 100 + (seed % 50), 0.025);
};

const fundamentals = (symbol) => {
  const seed = symbol.charCodeAt(0);
  return {
    marketCap: `$${(seed * 12.7).toFixed(1)}B`,
    pe: (15 + (seed % 20)).toFixed(1),
    eps: (2 + (seed % 7) * 0.4).toFixed(2),
    dividend: ((seed % 5) * 0.4).toFixed(2) + '%',
    beta: (0.8 + (seed % 10) * 0.07).toFixed(2),
    high52: (180 + (seed % 60)).toFixed(2),
    low52: (60 + (seed % 40)).toFixed(2),
    volume: `${(seed % 80 + 20).toFixed(1)}M`,
  };
};

module.exports = {
  indices,
  signals,
  news,
  watchlist,
  sectors,
  notifications,
  accuracy,
  marketStatus,
  priceHistory,
  fundamentals,
  sparkline,
};
