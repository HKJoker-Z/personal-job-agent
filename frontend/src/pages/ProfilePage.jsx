import React, { useEffect, useState } from "react";
import { apiJson } from "../api/client";

const sections = ["Basic Information", "Professional Summary", "Work Experience", "Education", "Projects", "Skills", "Languages", "Certifications", "Job Preferences", "Revision History"];

export function ProfilePage() {
  const [profile, setProfile] = useState(null); const [error, setError] = useState(""); const [saved, setSaved] = useState(false);
  useEffect(() => { apiJson("/api/profile").then(setProfile).catch((e) => setError(e.message)); }, []);
  async function save(event) {
    event.preventDefault(); setError(""); setSaved(false);
    try {
      const next = await apiJson("/api/profile", { method: "PUT", body: { revision: profile.revision, headline: profile.headline, professional_summary: profile.professional_summary, current_location: profile.current_location, phone: profile.phone, public_email: profile.public_email || null, website: profile.website, linkedin_url: profile.linkedin_url, github_url: profile.github_url } });
      setProfile(next); setSaved(true);
    } catch (e) { setError(e.message); }
  }
  if (!profile) return <section className="panel"><h2>Career Profile</h2><p>{error || "Loading…"}</p></section>;
  return <section className="panel form-panel"><h2>Career Profile</h2>
    <p>Completeness: {profile.completeness?.score || 0}% · Missing: {(profile.completeness?.missing_sections || []).join(", ") || "none"}</p>
    <div className="feature-strip">{sections.map((name) => <span key={name}>{name}</span>)}</div>
    <form onSubmit={save}>
      <label>Headline<input value={profile.headline || ""} onChange={(e) => setProfile({ ...profile, headline: e.target.value })} /></label>
      <label>Location<input value={profile.current_location || ""} onChange={(e) => setProfile({ ...profile, current_location: e.target.value })} /></label>
      <label>Professional Summary<textarea value={profile.professional_summary || ""} onChange={(e) => setProfile({ ...profile, professional_summary: e.target.value })} /></label>
      {error && <div className="error" role="alert">{error}</div>}{saved && <p role="status">Profile saved.</p>}
      <button type="submit">Save Profile</button>
    </form>
    <p className="muted">Facts marked confirmed are the only facts future AI features may treat as verified.</p>
  </section>;
}
