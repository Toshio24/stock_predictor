// Signal — client-side glue. Vanilla JS, no framework.
(function () {
  'use strict';

  // ---------- theme ----------------------------------------------------------
  const html = document.documentElement;
  const setTheme = (dark) => {
    html.classList.toggle('dark', dark);
    localStorage.setItem('signal:theme', dark ? 'dark' : 'light');
    const tl = document.querySelector('.theme-light');
    const td = document.querySelector('.theme-dark');
    if (tl && td) {
      tl.classList.toggle('hidden', dark);
      td.classList.toggle('hidden', !dark);
    }
  };
  // sync icon state on load
  setTheme(html.classList.contains('dark'));

  const themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) themeBtn.addEventListener('click', () => setTheme(!html.classList.contains('dark')));

  // ---------- sidebar collapse / mobile -------------------------------------
  const sidebar = document.getElementById('sidebar');
  const collapseBtn = document.getElementById('sidebar-collapse');
  const mobileMenu = document.getElementById('mobile-menu');
  const backdrop = document.getElementById('sidebar-backdrop');

  const restoreCollapsed = localStorage.getItem('signal:sidebar') === 'collapsed';
  if (restoreCollapsed && sidebar && window.innerWidth >= 1024) sidebar.classList.add('collapsed');

  if (collapseBtn) {
    collapseBtn.addEventListener('click', () => {
      sidebar.classList.toggle('collapsed');
      localStorage.setItem('signal:sidebar', sidebar.classList.contains('collapsed') ? 'collapsed' : 'open');
    });
  }
  if (mobileMenu) {
    mobileMenu.addEventListener('click', () => {
      sidebar.classList.add('mobile-open');
      backdrop.classList.add('open');
    });
  }
  if (backdrop) {
    backdrop.addEventListener('click', () => {
      sidebar.classList.remove('mobile-open');
      backdrop.classList.remove('open');
    });
  }

  // ---------- dropdown plumbing ---------------------------------------------
  const wireDropdown = (triggerId, panelId) => {
    const t = document.getElementById(triggerId);
    const p = document.getElementById(panelId);
    if (!t || !p) return;
    t.addEventListener('click', (e) => {
      e.stopPropagation();
      // close other dropdowns
      document.querySelectorAll('.dropdown.open').forEach((d) => { if (d !== p) d.classList.remove('open'); });
      p.classList.toggle('open');
    });
    p.addEventListener('click', (e) => e.stopPropagation());
  };
  wireDropdown('notif-trigger', 'notif-dropdown');
  wireDropdown('avatar-trigger', 'avatar-dropdown');

  document.addEventListener('click', () => {
    document.querySelectorAll('.dropdown.open').forEach((d) => d.classList.remove('open'));
  });

  // ---------- notification actions ------------------------------------------
  const notifDropdown = document.getElementById('notif-dropdown');
  if (notifDropdown) {
    notifDropdown.addEventListener('click', (e) => {
      const action = e.target.closest('[data-action]');
      if (!action) return;
      e.preventDefault();
      e.stopPropagation();
      if (action.dataset.action === 'mark-all') {
        notifDropdown.querySelectorAll('[data-notif-id]').forEach((row) => row.classList.add('opacity-60'));
        toast('All notifications marked as read');
      }
      if (action.dataset.action === 'delete') {
        const row = action.closest('[data-notif-id]');
        if (row) {
          row.style.transition = 'opacity .2s, transform .2s';
          row.style.opacity = '0';
          row.style.transform = 'translateX(8px)';
          setTimeout(() => row.remove(), 220);
        }
      }
    });
  }

  // ---------- global search --------------------------------------------------
  const search = document.getElementById('global-search');
  const results = document.getElementById('search-results');
  let searchTimer = null;
  const renderResults = (data) => {
    if (!results) return;
    const hasAny = (data.tickers && data.tickers.length) || (data.pages && data.pages.length);
    if (!hasAny) {
      results.innerHTML = '<div class="px-4 py-6 text-center text-[13px]" style="color: var(--text-muted);">No results</div>';
      results.classList.add('open');
      return;
    }
    let html = '';
    if (data.tickers.length) {
      html += '<div class="px-3 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-widest" style="color: var(--text-muted);">Tickers</div>';
      data.tickers.forEach((t) => {
        html += `<a href="/ticker/${t.ticker}" class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/5">
          <span class="ticker-badge">${t.ticker}</span>
          <span class="text-[13px] flex-1 truncate" style="color: var(--text);">${t.name}</span>
          <span class="sentiment-badge ${t.signal}">${t.score}</span>
        </a>`;
      });
    }
    if (data.pages.length) {
      html += '<div class="px-3 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-widest" style="color: var(--text-muted);">Pages</div>';
      data.pages.forEach((p) => {
        html += `<a href="${p.href}" class="block px-3 py-2 text-[13px] rounded-lg hover:bg-white/5" style="color: var(--text);">${p.label}</a>`;
      });
    }
    results.innerHTML = html;
    results.classList.add('open');
  };
  if (search) {
    search.addEventListener('input', (e) => {
      clearTimeout(searchTimer);
      const q = e.target.value.trim();
      if (!q) { results.classList.remove('open'); return; }
      searchTimer = setTimeout(() => {
        fetch('/api/search?q=' + encodeURIComponent(q))
          .then((r) => r.json())
          .then(renderResults)
          .catch(() => {});
      }, 120);
    });
    search.addEventListener('focus', () => { if (search.value.trim()) results.classList.add('open'); });
    search.addEventListener('click', (e) => e.stopPropagation());
    if (results) results.addEventListener('click', (e) => e.stopPropagation());
  }

  // ---------- keyboard shortcuts --------------------------------------------
  document.addEventListener('keydown', (e) => {
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      if (search) { search.focus(); search.select(); }
    }
    if (mod && e.key.toLowerCase() === 'r' && e.shiftKey === false && !e.repeat) {
      // do not block native refresh — only handle plain Cmd+R is browser's. Use Cmd+Shift+R reserved.
    }
    if (e.key === 'Escape') {
      document.querySelectorAll('.dropdown.open').forEach((d) => d.classList.remove('open'));
      if (search) search.blur();
    }
  });

  // ---------- toast ----------------------------------------------------------
  const host = document.getElementById('toast-host');
  window.toast = function (message, opts = {}) {
    if (!host) return;
    const el = document.createElement('div');
    el.className = 'toast';
    if (opts.type === 'success') el.style.borderLeft = '3px solid var(--bull)';
    if (opts.type === 'error') el.style.borderLeft = '3px solid var(--bear)';
    el.textContent = message;
    host.appendChild(el);
    setTimeout(() => {
      el.style.transition = 'opacity .3s, transform .3s';
      el.style.opacity = '0';
      el.style.transform = 'translateX(20px)';
      setTimeout(() => el.remove(), 320);
    }, opts.duration || 3200);
  };

  // ---------- list stagger (re-fire on hydration) ---------------------------
  document.querySelectorAll('[data-stagger]').forEach((el) => {
    Array.from(el.children).forEach((child, i) => {
      child.style.animationDelay = (i * 0.06) + 's';
    });
  });

  // ---------- auth forms (Firebase) -----------------------------------------
  // Firebase SDK loads as a module and may not be ready when this script
  // runs. Wait for the `signal-auth-ready` event before binding handlers.
  function wireAuth() {
    const Auth = window.SignalAuth;
    if (!Auth || !Auth.enabled) {
      // Auth not configured (missing FIREBASE_* env vars). Surface it so
      // users don't sit on a dead button thinking it's broken.
      document.querySelectorAll('form[data-auth], [data-auth-google], [data-logout]').forEach((el) => {
        el.addEventListener('click', (e) => {
          e.preventDefault();
          toast('Sign-in is not configured on this deploy', { type: 'error' });
        });
      });
      return;
    }

    async function handle(action, successMsg) {
      try {
        const user = await action();
        toast(successMsg.replace('{name}', user.displayName || user.email || ''), { type: 'success' });
        setTimeout(() => { window.location.href = '/'; }, 500);
      } catch (e) {
        toast(humanizeFirebaseError(e), { type: 'error' });
      }
    }

    document.querySelectorAll('form[data-auth]').forEach((form) => {
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        const data = Object.fromEntries(new FormData(form).entries());
        const kind = form.dataset.auth;
        if (kind === 'login') {
          handle(() => Auth.login(data.email, data.password), 'Welcome back');
        } else if (kind === 'signup') {
          handle(() => Auth.signup(data.email, data.password, data.name), 'Welcome, {name}');
        } else if (kind === 'forgot') {
          Auth.resetPassword(data.email)
            .then(() => toast('Reset link sent to ' + data.email, { type: 'success' }))
            .catch((err) => toast(humanizeFirebaseError(err), { type: 'error' }));
        }
      });
    });

    document.querySelectorAll('[data-auth-google]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        handle(() => Auth.loginGoogle(), 'Welcome, {name}');
      });
    });

    document.querySelectorAll('[data-logout]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        Auth.logout();
      });
    });
  }

  function humanizeFirebaseError(e) {
    const code = (e && e.code) || '';
    if (code === 'auth/invalid-credential' || code === 'auth/wrong-password' || code === 'auth/user-not-found') {
      return 'Incorrect email or password';
    }
    if (code === 'auth/email-already-in-use') return 'That email already has an account';
    if (code === 'auth/weak-password') return 'Password is too weak (min 6 characters)';
    if (code === 'auth/popup-closed-by-user') return 'Sign-in cancelled';
    if (code === 'auth/network-request-failed') return 'Network error — check your connection';
    return (e && e.message) || 'Something went wrong';
  }

  if (window.SignalAuth) wireAuth();
  else window.addEventListener('signal-auth-ready', wireAuth, { once: true });
})();
