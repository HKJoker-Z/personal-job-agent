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
import { DashboardPage } from "./pages/DashboardPage";
import { JobDetailPage, JobImportPage, JobLibraryPage } from "./pages/JobPages";
import { ApplicationBoardPage, ApplicationDetailPage } from "./pages/ApplicationPages";
import { TasksPage } from "./pages/TasksPage";
import { ApplicationPackageDetailPage, ApplicationPackagesPage, JobRankingPage } from "./pages/V203Pages";
import { AgentRunDetailPage, AgentRunsPage, ApprovalsPage } from "./pages/AgentPages";

export function App() {
  return <AuthProvider><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<ProtectedRoute />}><Route element={<AppLayout />}>
      <Route path="/workspace" element={<LegacyWorkspace initialTab="analyze" />} />
      <Route path="/analyze" element={<LegacyWorkspace initialTab="analyze" />} />
      <Route path="/history" element={<LegacyWorkspace initialTab="history" />} />
      <Route path="/project-knowledge" element={<LegacyWorkspace initialTab="knowledge" />} />
      <Route path="/monitoring" element={<LegacyWorkspace initialTab="monitoring" />} />
      <Route path="/evaluation" element={<LegacyWorkspace initialTab="monitoring" />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/jobs" element={<JobLibraryPage />} />
      <Route path="/jobs/import" element={<JobImportPage />} />
      <Route path="/jobs/:jobId" element={<JobDetailPage />} />
      <Route path="/job-ranking" element={<JobRankingPage />} />
      <Route path="/applications" element={<ApplicationBoardPage />} />
      <Route path="/applications/:applicationId/packages" element={<ApplicationPackagesPage />} />
      <Route path="/applications/:applicationId" element={<ApplicationDetailPage />} />
      <Route path="/application-packages/:packageId" element={<ApplicationPackageDetailPage />} />
      <Route path="/agent-runs" element={<AgentRunsPage />} />
      <Route path="/agent-runs/:runId" element={<AgentRunDetailPage />} />
      <Route path="/approvals" element={<ApprovalsPage />} />
      <Route path="/tasks" element={<TasksPage />} />
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
