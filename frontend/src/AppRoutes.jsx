import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthProvider";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { AppLayout } from "./components/AppLayout";
import { LegacyWorkspace } from "./legacy-workspace";
import { AccountPage } from "./pages/AccountPage";
import { AgentRunDetailPage, AgentRunsPage } from "./pages/AgentPages";
import { ArchitecturePage } from "./pages/ArchitecturePage";
import { DashboardPage } from "./pages/DashboardPage";
import { FeatureRemovedPage, NotFoundPage } from "./pages/FeatureStatePage";
import { LoginPage } from "./pages/LoginPage";
import { ProfilePage } from "./pages/ProfilePage";
import { ResumeDetailPage, ResumeImportPage, ResumeLibraryPage } from "./pages/ResumePages";

export function App() {
  return <AuthProvider><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<ProtectedRoute />}><Route element={<AppLayout />}>
      <Route index element={<Navigate to="/dashboard" replace />} />
      <Route path="/workspace" element={<Navigate to="/dashboard" replace />} />
      <Route path="/analyze" element={<LegacyWorkspace initialTab="analyze" />} />
      <Route path="/history" element={<LegacyWorkspace initialTab="history" />} />
      <Route path="/project-knowledge" element={<LegacyWorkspace initialTab="knowledge" />} />
      <Route path="/monitoring" element={<LegacyWorkspace initialTab="monitoring" />} />
      <Route path="/evaluation" element={<LegacyWorkspace initialTab="monitoring" />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/jobs/*" element={<FeatureRemovedPage />} />
      <Route path="/job-ranking/*" element={<FeatureRemovedPage />} />
      <Route path="/applications/*" element={<FeatureRemovedPage />} />
      <Route path="/application-packages/*" element={<FeatureRemovedPage />} />
      <Route path="/agent-runs" element={<AgentRunsPage />} />
      <Route path="/agent-runs/:runId" element={<AgentRunDetailPage />} />
      <Route path="/architecture" element={<ArchitecturePage />} />
      <Route path="/approvals/*" element={<FeatureRemovedPage />} />
      <Route path="/tasks/*" element={<FeatureRemovedPage />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/resumes" element={<ResumeLibraryPage />} />
      <Route path="/resumes/import" element={<ResumeImportPage />} />
      <Route path="/resumes/:resumeId" element={<ResumeDetailPage />} />
      <Route path="/account" element={<AccountPage />} />
    </Route></Route>
    <Route path="*" element={<NotFoundPage />} />
  </Routes></AuthProvider>;
}
