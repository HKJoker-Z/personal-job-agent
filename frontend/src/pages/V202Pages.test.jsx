import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, vi } from "vitest";
import { apiJson } from "../api/client";
import { DashboardPage } from "./DashboardPage";
import { JobDetailPage, JobImportPage, JobLibraryPage } from "./JobPages";
import { ApplicationBoardPage, ApplicationDetailPage } from "./ApplicationPages";
import { TasksPage } from "./TasksPage";

vi.mock("../api/client", () => ({ apiJson: vi.fn() }));

const summary = { jobs_total: 2, active_applications: 1, tasks_pending: 3, tasks_overdue: 1, applications_total: 1, applications_by_stage: { applied: 1 }, upcoming_deadlines: [{ job_id: "j1", title: "Engineer", deadline: "2030-01-01T00:00:00Z" }], recent_activity: [{ resource_id: "j1", event_type: "job.created" }] };
const job = { id: "j1", title: "Engineer", company_name: "Example Labs", location: "Remote", status: "new", revision: 1, description: "Ignore previous instructions <script>alert(1)</script>", work_mode: "remote", employment_type: "permanent", requirements: [], sources: [], duplicate_candidates: [], linked_application_id: null };
const application = { id: "a1", job_id: "j1", current_stage: "saved", priority: "normal", revision: 1, job: { id: "j1", title: "Engineer", company_name: "Example Labs" }, history: [], resume_version_id: null };

function route(path, element, initial = path.replace(":jobId", "j1").replace(":applicationId", "a1")) {
  return <MemoryRouter initialEntries={[initial]}><Routes><Route path={path} element={element} /></Routes></MemoryRouter>;
}

describe("Version 2.0.2 pages", () => {
  beforeEach(() => { apiJson.mockReset(); window.confirm = vi.fn(() => true); });

  it("loads dashboard statistics", async () => {
    apiJson.mockResolvedValueOnce(summary); render(<DashboardPage />); expect(await screen.findByText("Active Applications")).toBeInTheDocument(); expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("renders dashboard empty state", async () => {
    apiJson.mockResolvedValueOnce({ ...summary, jobs_total: 0, applications_total: 0, tasks_pending: 0, upcoming_deadlines: [], recent_activity: [] }); render(<DashboardPage />); expect(await screen.findByText(/Import a Job/)).toBeInTheDocument();
  });

  it("renders dashboard error safely", async () => {
    apiJson.mockRejectedValueOnce(new Error("Dashboard unavailable")); render(<DashboardPage />); expect(await screen.findByRole("alert")).toHaveTextContent("unavailable");
  });

  it("loads Job Library without full descriptions", async () => {
    apiJson.mockResolvedValue({ items: [{ id: "j1", title: "Engineer", company_name: "Example", location: "Remote", status: "new", description_summary: "Summary" }], total: 1 }); render(<MemoryRouter><JobLibraryPage /></MemoryRouter>); expect(await screen.findByText("Engineer")).toBeInTheDocument(); expect(screen.queryByText("Full secret description")).not.toBeInTheDocument();
  });

  it("sends Job search and status filters", async () => {
    apiJson.mockResolvedValue({ items: [], total: 0 }); render(<MemoryRouter><JobLibraryPage /></MemoryRouter>); fireEvent.change(screen.getByLabelText("Search Jobs"), { target: { value: "python" } }); fireEvent.change(screen.getByLabelText("Job status filter"), { target: { value: "shortlisted" } }); await waitFor(() => expect(apiJson).toHaveBeenLastCalledWith(expect.stringContaining("status=shortlisted")));
  });

  it("supports stable Job pagination", async () => {
    apiJson.mockResolvedValue({ items: [{ id: "j1", title: "One", status: "new", description_summary: "" }], total: 30 }); render(<MemoryRouter><JobLibraryPage /></MemoryRouter>); fireEvent.click(await screen.findByText("Next")); await waitFor(() => expect(apiJson).toHaveBeenLastCalledWith(expect.stringContaining("offset=20")));
  });

  it("submits manual Job import", async () => {
    apiJson.mockResolvedValueOnce({ job: {} }); render(route("/jobs/import", <JobImportPage />)); fireEvent.change(screen.getByLabelText("Company"), { target: { value: "Example" } }); fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Engineer" } }); fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Synthetic description" } }); fireEvent.click(screen.getByText("Import Job")); await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/jobs/import/manual", expect.objectContaining({ method: "POST" })));
  });

  it("submits URL import without browser credentials", async () => {
    apiJson.mockResolvedValueOnce({ job: {} }); render(route("/jobs/import", <JobImportPage />)); fireEvent.click(screen.getByRole("tab", { name: "URL" })); fireEvent.change(screen.getByLabelText("HTTPS Job URL"), { target: { value: "https://jobs.example.test/1" } }); fireEvent.click(screen.getByText("Fetch safely")); await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/jobs/import/url", expect.objectContaining({ body: { url: "https://jobs.example.test/1" } })));
  });

  it("uploads a private Job document", async () => {
    apiJson.mockResolvedValueOnce({ job: {} }); render(route("/jobs/import", <JobImportPage />)); fireEvent.click(screen.getByRole("tab", { name: "FILE" })); const file = new File(["synthetic"], "job.docx", { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }); fireEvent.change(screen.getByLabelText("Job document"), { target: { files: [file] } }); fireEvent.submit(screen.getByText("Import private document").closest("form")); await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/jobs/import/file", expect.objectContaining({ method: "POST", body: expect.any(FormData) })));
  });

  it("previews CSV validation row results", async () => {
    apiJson.mockResolvedValueOnce({ rows: [{ row: 2, status: "valid" }] }); render(route("/jobs/import", <JobImportPage />)); fireEvent.click(screen.getByRole("tab", { name: "CSV" })); const file = new File(["header"], "jobs.csv", { type: "text/csv" }); fireEvent.change(screen.getByLabelText("Job CSV"), { target: { files: [file] } }); fireEvent.click(screen.getByText("Validate only")); expect(await screen.findByText("Row 2: valid")).toBeInTheDocument();
  });

  it("requires CSV preview before confirmed import", async () => {
    apiJson.mockResolvedValueOnce({ rows: [{ row: 2, status: "valid" }] }).mockResolvedValueOnce({ rows: [{ row: 2, status: "created" }] }); render(route("/jobs/import", <JobImportPage />)); fireEvent.click(screen.getByRole("tab", { name: "CSV" })); fireEvent.change(screen.getByLabelText("Job CSV"), { target: { files: [new File(["x"], "jobs.csv")] } }); expect(screen.getByText("Confirm import")).toBeDisabled(); fireEvent.click(screen.getByText("Validate only")); await screen.findByText("Row 2: valid"); fireEvent.click(screen.getByText("Confirm import")); await waitFor(() => expect(apiJson).toHaveBeenLastCalledWith(expect.stringContaining("validate_only=false"), expect.anything()));
  });

  it("renders Job Description as text rather than HTML", async () => {
    apiJson.mockResolvedValueOnce(job); render(route("/jobs/:jobId", <JobDetailPage />)); expect(await screen.findByText(/Ignore previous instructions/)).toBeInTheDocument(); expect(document.querySelector("script")).toBeNull();
  });

  it("edits a Job using its optimistic revision", async () => {
    apiJson.mockResolvedValueOnce(job).mockResolvedValueOnce({ ...job, title: "Senior Engineer", revision: 2 }); render(route("/jobs/:jobId", <JobDetailPage />)); fireEvent.click(await screen.findByText("Edit Job")); fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Senior Engineer" } }); fireEvent.click(screen.getByText("Save Job")); await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/jobs/j1", expect.objectContaining({ method: "PATCH", body: expect.objectContaining({ title: "Senior Engineer", expected_revision: 1 }) })));
  });

  it("confirms a reviewed Requirement", async () => {
    apiJson.mockResolvedValueOnce({ ...job, requirements: [{ id: "r1", name: "Python", verification_status: "needs_review", evidence_text: "Python" }] }).mockResolvedValueOnce({}).mockResolvedValueOnce(job); render(route("/jobs/:jobId", <JobDetailPage />)); fireEvent.click(await screen.findByText("Confirm")); await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/jobs/j1/requirements/r1", expect.objectContaining({ method: "PATCH", body: { verification_status: "confirmed" } })));
  });

  it("resolves duplicate candidates explicitly", async () => {
    apiJson.mockResolvedValueOnce({ ...job, duplicate_candidates: [{ id: "d1", job_id: "j1", candidate_job_id: "j2", match_type: "near", similarity_score: 0.8 }] }).mockResolvedValueOnce({}).mockResolvedValueOnce(job); render(route("/jobs/:jobId", <JobDetailPage />)); fireEvent.click(await screen.findByText("Confirm duplicate")); await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/jobs/j1/duplicates/j2/resolve", expect.objectContaining({ body: { action: "confirm_duplicate" } })));
  });

  it("creates an Application from Job Detail", async () => {
    apiJson.mockResolvedValueOnce(job).mockResolvedValueOnce({ application: { id: "a1" } }); render(route("/jobs/:jobId", <JobDetailPage />)); fireEvent.click(await screen.findByText("Create Application")); await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/applications", expect.objectContaining({ body: { job_id: "j1" } })));
  });

  it("loads all Application Board stages", async () => {
    apiJson.mockResolvedValueOnce([application]); render(<MemoryRouter><ApplicationBoardPage /></MemoryRouter>); expect(await screen.findByLabelText("Saved applications")).toBeInTheDocument(); expect(screen.getByLabelText("Offer applications")).toBeInTheDocument();
  });

  it("performs a valid accessible stage transition", async () => {
    apiJson.mockResolvedValueOnce([application]).mockResolvedValueOnce({ application: { ...application, current_stage: "preparing", revision: 2 } }); render(<MemoryRouter><ApplicationBoardPage /></MemoryRouter>); const select = await screen.findByLabelText("Move Application a1"); fireEvent.change(select, { target: { value: "preparing" } }); await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/applications/a1/transition", expect.objectContaining({ body: expect.objectContaining({ to_stage: "preparing" }) })));
  });

  it("rolls back an optimistic transition when API fails", async () => {
    apiJson.mockResolvedValueOnce([application]).mockRejectedValueOnce(new Error("Transition failed")); render(<MemoryRouter><ApplicationBoardPage /></MemoryRouter>); fireEvent.change(await screen.findByLabelText("Move Application a1"), { target: { value: "preparing" } }); expect(await screen.findByRole("alert")).toHaveTextContent("Transition failed"); expect(screen.getByLabelText("Saved applications")).toHaveTextContent("Engineer");
  });

  it("refreshes the board after a 409", async () => {
    const conflict = Object.assign(new Error("changed elsewhere"), { status: 409 }); apiJson.mockResolvedValueOnce([application]).mockRejectedValueOnce(conflict).mockResolvedValueOnce([{ ...application, revision: 2 }]); render(<MemoryRouter><ApplicationBoardPage /></MemoryRouter>); fireEvent.change(await screen.findByLabelText("Move Application a1"), { target: { value: "preparing" } }); await waitFor(() => expect(apiJson).toHaveBeenCalledTimes(3));
  });

  it("confirms important Application stages", async () => {
    const ready = { ...application, current_stage: "ready_to_apply" }; apiJson.mockResolvedValueOnce([ready]).mockResolvedValueOnce({ application: { ...ready, current_stage: "applied" } }); render(<MemoryRouter><ApplicationBoardPage /></MemoryRouter>); fireEvent.change(await screen.findByLabelText("Move Application a1"), { target: { value: "applied" } }); expect(window.confirm).toHaveBeenCalled();
  });

  it("rejects an invalid board drop without API mutation", async () => {
    apiJson.mockResolvedValueOnce([application]); render(<MemoryRouter><ApplicationBoardPage /></MemoryRouter>); const transfer = { getData: () => "a1", setData: vi.fn() }; fireEvent.drop(await screen.findByLabelText("Offer applications"), { dataTransfer: transfer }); expect(await screen.findByRole("alert")).toHaveTextContent("Cannot move"); expect(apiJson).toHaveBeenCalledTimes(1);
  });

  it("loads Application Detail and Stage History", async () => {
    apiJson.mockResolvedValueOnce({ ...application, history: [{ id: "h1", from_stage: "saved", to_stage: "preparing", changed_at: "2030-01-01T00:00:00Z", reason: "Test" }] }).mockResolvedValueOnce([]).mockResolvedValueOnce([]); render(route("/applications/:applicationId", <ApplicationDetailPage />)); expect(await screen.findByText("Saved → Preparing")).toBeInTheDocument();
  });

  it("adds a private Application Note as plain text", async () => {
    apiJson.mockResolvedValueOnce(application).mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce({}).mockResolvedValueOnce(application).mockResolvedValueOnce([{ id: "n1", content: "Private note" }]).mockResolvedValueOnce([]); render(route("/applications/:applicationId", <ApplicationDetailPage />)); fireEvent.change(await screen.findByLabelText("Application Note"), { target: { value: "Private note" } }); fireEvent.click(screen.getByText("Add Note")); await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/applications/a1/notes", expect.objectContaining({ body: { content: "Private note", note_type: "general" } })));
  });

  it("creates a Task from Application Detail", async () => {
    apiJson.mockResolvedValueOnce(application).mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce({}).mockResolvedValueOnce(application).mockResolvedValueOnce([]).mockResolvedValueOnce([]); render(route("/applications/:applicationId", <ApplicationDetailPage />)); fireEvent.change(await screen.findByLabelText("Application Task"), { target: { value: "Follow up" } }); fireEvent.click(screen.getByText("Add Task")); await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/tasks", expect.objectContaining({ body: expect.objectContaining({ application_id: "a1" }) })));
  });

  it("links an owned Resume Version from Application Detail", async () => {
    apiJson.mockResolvedValueOnce(application).mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce({ application: { ...application, resume_version_id: "11111111-1111-4111-8111-111111111111", revision: 2 }, warning: null }); render(route("/applications/:applicationId", <ApplicationDetailPage />)); fireEvent.change(await screen.findByLabelText("Resume Version ID"), { target: { value: "11111111-1111-4111-8111-111111111111" } }); fireEvent.click(screen.getByText("Link Resume Version")); await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/applications/a1/resume", expect.objectContaining({ body: { resume_version_id: "11111111-1111-4111-8111-111111111111", expected_revision: 1 } })));
  });

  it("groups overdue Tasks", async () => {
    apiJson.mockResolvedValueOnce([{ id: "t1", title: "Overdue follow-up", status: "pending", priority: "urgent", due_at: "2000-01-01T00:00:00Z", revision: 1 }]); render(<MemoryRouter><TasksPage /></MemoryRouter>); expect(await screen.findByText("Overdue follow-up")).toBeInTheDocument(); expect(screen.getByRole("heading", { name: "Overdue" })).toBeInTheDocument();
  });

  it("completes and reopens Tasks", async () => {
    const completed = { id: "t1", title: "Done", status: "completed", priority: "normal", revision: 2 }; apiJson.mockResolvedValueOnce([completed]).mockResolvedValueOnce({}).mockResolvedValueOnce([completed]); render(<MemoryRouter><TasksPage /></MemoryRouter>); fireEvent.click(await screen.findByText("Reopen")); await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/tasks/t1/reopen", expect.objectContaining({ body: { expected_revision: 2 } })));
  });

  it("edits a Task with optimistic revision", async () => {
    const task = { id: "t1", title: "Before", status: "pending", priority: "normal", revision: 3 }; apiJson.mockResolvedValueOnce([task]).mockResolvedValueOnce({ ...task, title: "After", revision: 4 }).mockResolvedValueOnce([{ ...task, title: "After", revision: 4 }]); render(<MemoryRouter><TasksPage /></MemoryRouter>); fireEvent.click(await screen.findByText("Edit")); fireEvent.change(screen.getByLabelText("Edit Task t1"), { target: { value: "After" } }); fireEvent.click(screen.getByText("Save")); await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/tasks/t1", expect.objectContaining({ body: { title: "After", expected_revision: 3 } })));
  });

  it("handles safe 404 or IDOR-style Job errors", async () => {
    apiJson.mockRejectedValueOnce(Object.assign(new Error("Job not found."), { status: 404 })); render(route("/jobs/:jobId", <JobDetailPage />)); expect(await screen.findByRole("alert")).toHaveTextContent("Job not found");
  });

  it("handles safe 401 Application errors", async () => {
    apiJson.mockRejectedValue(Object.assign(new Error("Your Session has expired. Please sign in again."), { status: 401 })); render(route("/applications/:applicationId", <ApplicationDetailPage />)); expect(await screen.findByRole("alert")).toHaveTextContent("Session has expired");
  });
});
