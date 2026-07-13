import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./styles.css";
import { AuthProvider } from "./auth/AuthProvider";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { AppLayout } from "./components/AppLayout";
import { ErrorBoundary, LegacyWorkspace } from "./legacy-workspace";
import { AccountPage } from "./pages/AccountPage";
import { LoginPage } from "./pages/LoginPage";
import { ProfilePage } from "./pages/ProfilePage";
import { ResumeDetailPage, ResumeImportPage, ResumeLibraryPage } from "./pages/ResumePages";

export function App() {
  return <AuthProvider><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<ProtectedRoute />}><Route element={<AppLayout />}>
      <Route path="/workspace" element={<LegacyWorkspace />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/resumes" element={<ResumeLibraryPage />} />
      <Route path="/resumes/import" element={<ResumeImportPage />} />
      <Route path="/resumes/:resumeId" element={<ResumeDetailPage />} />
      <Route path="/account" element={<AccountPage />} />
    </Route></Route>
    <Route path="*" element={<Navigate to="/workspace" replace />} />
  </Routes></AuthProvider>;
}

const rootElement = document.getElementById("root");
if (!rootElement) document.body.textContent = "Frontend failed to start.";
else createRoot(rootElement).render(<ErrorBoundary><BrowserRouter><App /></BrowserRouter></ErrorBoundary>);
