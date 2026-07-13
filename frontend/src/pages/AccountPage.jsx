import React, { useState } from "react";
import { apiJson } from "../api/client";
import { useAuth } from "../auth/AuthProvider";

export function AccountPage() {
  const { user, logout } = useAuth(); const [currentPassword, setCurrent] = useState(""); const [newPassword, setNew] = useState(""); const [message, setMessage] = useState("");
  async function change(event) { event.preventDefault(); try { await apiJson("/api/auth/change-password", { method: "POST", body: { current_password: currentPassword, new_password: newPassword } }); setCurrent(""); setNew(""); setMessage("Password changed; other Sessions were revoked."); } catch (e) { setMessage(e.message); } }
  return <section className="panel form-panel"><h2>Account Settings</h2><p>{user?.display_name} · {user?.role}</p><form onSubmit={change}><label>Current password<input type="password" autoComplete="current-password" value={currentPassword} onChange={(e) => setCurrent(e.target.value)} /></label><label>New passphrase<input type="password" autoComplete="new-password" value={newPassword} onChange={(e) => setNew(e.target.value)} /></label><button type="submit">Change password</button></form>{message && <p role="status">{message}</p>}<button type="button" onClick={() => logout(false)}>Log out</button><button type="button" onClick={() => logout(true)}>Log out all Sessions</button></section>;
}
