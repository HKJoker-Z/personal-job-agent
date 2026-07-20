import React, { useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import {
  clearRememberedEmail,
  loadRememberedEmail,
  normalizeRememberedEmail,
  saveRememberedEmail,
} from "../auth/login-storage";

export function LoginPage() {
  const { user, login, initialized } = useAuth();
  const location = useLocation();
  const initialEmail = loadRememberedEmail();
  const [email, setEmail] = useState(initialEmail);
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [rememberEmail, setRememberEmail] = useState(Boolean(initialEmail));
  const [capsLock, setCapsLock] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  if (user) return <Navigate to={location.state?.from || "/dashboard"} replace />;
  async function submit(event) {
    event.preventDefault();
    if (loading) return;
    setLoading(true); setError("");
    try {
      const normalizedEmail = normalizeRememberedEmail(email);
      await login(normalizedEmail || email.trim(), password, rememberMe);
      if (rememberEmail) saveRememberedEmail(email);
      else clearRememberedEmail();
    }
    catch { setError("Unable to sign in with those credentials."); }
    finally { setLoading(false); }
  }
  return <main className="login-shell"><section className="panel form-panel login-panel">
    <div><span className="eyebrow">Personal Job Agent</span><h1>Sign in</h1><p className="muted">Access your private analysis workspace.</p></div>
    {!initialized && <p className="security-notice">Administrator account has not been initialized. Use the secure server CLI.</p>}
    <form onSubmit={submit} autoComplete="on">
      <label>Email<input aria-label="Email" type="email" inputMode="email" autoComplete="username" maxLength="320" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
      <label>Password<div className="password-field"><input aria-label="Password" type={show ? "text" : "password"} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => setCapsLock(e.getModifierState("CapsLock"))} onKeyUp={(e) => setCapsLock(e.getModifierState("CapsLock"))} onBlur={() => setCapsLock(false)} required /><button className="password-toggle" type="button" aria-label={show ? "Hide password" : "Show password"} aria-pressed={show} onClick={() => setShow((value) => !value)}>{show ? "Hide" : "Show"}</button></div></label>
      {capsLock && <p className="caps-lock" role="status">Caps Lock is on.</p>}
      <label className="checkbox-label"><input type="checkbox" checked={rememberMe} onChange={(e) => setRememberMe(e.target.checked)} /> Remember me</label>
      <p className="field-help">Stay signed in on this device. Your browser password manager may save the password; this application never stores the plaintext password.</p>
      <label className="checkbox-label"><input type="checkbox" checked={rememberEmail} onChange={(e) => { setRememberEmail(e.target.checked); if (!e.target.checked) clearRememberedEmail(); }} /> Remember email</label>
      {error && <div className="error" role="alert">{error}</div>}
      <button type="submit" disabled={loading} aria-busy={loading}>{loading ? "Signing in…" : "Sign in"}</button>
    </form>
  </section></main>;
}
