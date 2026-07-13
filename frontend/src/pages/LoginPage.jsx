import React, { useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";

export function LoginPage() {
  const { user, login, initialized } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  if (user) return <Navigate to={location.state?.from || "/workspace"} replace />;
  async function submit(event) {
    event.preventDefault(); setLoading(true); setError("");
    try { await login(email, password); }
    catch (requestError) { setError(requestError.message); }
    finally { setLoading(false); }
  }
  return <main className="app-shell"><section className="panel form-panel">
    <h1>Sign in</h1>
    {!initialized && <p className="security-notice">Administrator account has not been initialized. Use the secure server CLI.</p>}
    <form onSubmit={submit}>
      <label>Email<input aria-label="Email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
      <label>Password<input aria-label="Password" type={show ? "text" : "password"} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
      <label><input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> Show password</label>
      {error && <div className="error" role="alert">{error}</div>}
      <button type="submit" disabled={loading}>{loading ? "Signing in…" : "Sign in"}</button>
    </form>
  </section></main>;
}
