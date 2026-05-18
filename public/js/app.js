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

  // ---------- auth forms (mock) ---------------------------------------------
  document.querySelectorAll('form[data-auth]').forEach((form) => {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const data = Object.fromEntries(new FormData(form).entries());
      const kind = form.dataset.auth;
      const url = kind === 'login' ? '/api/auth/login' : kind === 'signup' ? '/api/auth/signup' : null;
      if (!url) {
        toast('Reset link sent to ' + (data.email || 'your inbox'), { type: 'success' });
        return;
      }
      fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
        .then((r) => r.json())
        .then((res) => {
          if (res.ok) {
            localStorage.setItem('signal:user', JSON.stringify(res.user));
            toast('Welcome, ' + res.user.name, { type: 'success' });
            setTimeout(() => { window.location.href = '/'; }, 600);
          }
        })
        .catch(() => toast('Something went wrong', { type: 'error' }));
    });
  });
})();
