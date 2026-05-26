// Firebase auth — client-side.
//
// Loaded as an ES module. Initializes Firebase with the config injected by
// the server (window.firebaseConfig), exposes window.SignalAuth.{login,signup,
// loginGoogle,logout}, and keeps a signed HTTP-only session cookie in sync
// with the user's current Firebase ID token via onIdTokenChanged.

import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.13.0/firebase-app.js';
import {
  getAuth,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInWithPopup,
  GoogleAuthProvider,
  signOut,
  onIdTokenChanged,
  updateProfile,
  sendPasswordResetEmail,
} from 'https://www.gstatic.com/firebasejs/10.13.0/firebase-auth.js';

const cfg = window.firebaseConfig || {};
const enabled = Boolean(cfg.apiKey && cfg.projectId);

let auth = null;
if (enabled) {
  const app = initializeApp(cfg);
  auth = getAuth(app);
}

async function syncSession(user) {
  try {
    if (!user) {
      await fetch('/api/auth/session', { method: 'DELETE' });
      return;
    }
    const idToken = await user.getIdToken();
    await fetch('/api/auth/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idToken }),
    });
  } catch (e) {
    console.warn('[auth] session sync failed', e);
  }
}

if (auth) {
  onIdTokenChanged(auth, syncSession);
}

window.SignalAuth = {
  enabled,
  async login(email, password) {
    if (!auth) throw new Error('Auth is not configured');
    const cred = await signInWithEmailAndPassword(auth, email, password);
    await syncSession(cred.user);
    return cred.user;
  },
  async signup(email, password, name) {
    if (!auth) throw new Error('Auth is not configured');
    const cred = await createUserWithEmailAndPassword(auth, email, password);
    if (name) {
      try { await updateProfile(cred.user, { displayName: name }); } catch (_) {}
    }
    await syncSession(cred.user);
    return cred.user;
  },
  async loginGoogle() {
    if (!auth) throw new Error('Auth is not configured');
    const provider = new GoogleAuthProvider();
    const cred = await signInWithPopup(auth, provider);
    await syncSession(cred.user);
    return cred.user;
  },
  async resetPassword(email) {
    if (!auth) throw new Error('Auth is not configured');
    await sendPasswordResetEmail(auth, email);
  },
  async logout() {
    if (auth) await signOut(auth);
    await fetch('/api/auth/session', { method: 'DELETE' });
    window.location.href = '/login';
  },
};

window.dispatchEvent(new CustomEvent('signal-auth-ready'));
