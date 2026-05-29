// Minimal i18n for the Express/EJS frontend.
//
// gettext-style: the English string is the key. A translation file maps
// English -> target language. Missing keys fall back to the English string,
// so an untranslated label degrades gracefully instead of crashing.
//
// Add a language by dropping `locales/<code>.json` next to en (which is
// implicit — English is the source) and adding the code to SUPPORTED.

const fs = require('fs');
const path = require('path');

const SUPPORTED = ['en', 'zh'];
const DEFAULT_LANG = 'en';

const dicts = {};
for (const code of SUPPORTED) {
  if (code === 'en') continue; // English is the source language (identity)
  try {
    const raw = fs.readFileSync(path.join(__dirname, '..', 'locales', `${code}.json`), 'utf8');
    dicts[code] = JSON.parse(raw);
  } catch (_) {
    dicts[code] = {};
  }
}

function normalizeLang(lang) {
  if (!lang) return DEFAULT_LANG;
  const base = String(lang).toLowerCase().split('-')[0];
  return SUPPORTED.includes(base) ? base : DEFAULT_LANG;
}

// translate(lang, str) -> localized string (or the English source if missing).
function translate(lang, str) {
  const code = normalizeLang(lang);
  if (code === 'en') return str;
  const dict = dicts[code] || {};
  return Object.prototype.hasOwnProperty.call(dict, str) ? dict[str] : str;
}

module.exports = { SUPPORTED, DEFAULT_LANG, normalizeLang, translate };
