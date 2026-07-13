import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiJson } from "../api/client";

export function TasksPage() {
  const [items, setItems] = useState([]);
  const [showCompleted, setShowCompleted] = useState(false);
  const [priorityFilter, setPriorityFilter] = useState("");
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState("normal");
  const [dueAt, setDueAt] = useState("");
  const [editingId, setEditingId] = useState("");
  const [editingTitle, setEditingTitle] = useState("");
  const [error, setError] = useState("");
  const load = () => apiJson(`/api/tasks?sort=due_at${showCompleted ? "&status=completed" : ""}${priorityFilter ? `&priority=${priorityFilter}` : ""}`).then(setItems).catch((value) => setError(value.message));
  useEffect(() => { load(); }, [showCompleted, priorityFilter]);
  const groups = useMemo(() => {
    const now = new Date(); const todayEnd = new Date(); todayEnd.setHours(23, 59, 59, 999);
    return {
      Overdue: items.filter((item) => item.status !== "completed" && item.due_at && new Date(item.due_at) < now),
      Today: items.filter((item) => item.status !== "completed" && item.due_at && new Date(item.due_at) >= now && new Date(item.due_at) <= todayEnd),
      Upcoming: items.filter((item) => item.status !== "completed" && (!item.due_at || new Date(item.due_at) > todayEnd)),
      Completed: items.filter((item) => item.status === "completed"),
    };
  }, [items]);
  const action = async (task, name) => { try { await apiJson(`/api/tasks/${task.id}/${name}`, { method: "POST", body: { expected_revision: task.revision } }); await load(); } catch (value) { setError(value.message); } };
  return <section><div className="section-heading"><h2>Tasks</h2><div className="filter-bar"><label><input type="checkbox" checked={showCompleted} onChange={(event) => setShowCompleted(event.target.checked)} /> Show completed only</label><label>Priority<select aria-label="Task priority filter" value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)}><option value="">All</option><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select></label></div></div>{error ? <p role="alert">{error}</p> : null}
    <form className="inline-form" onSubmit={async (event) => { event.preventDefault(); try { const body = { title, task_type: "other", priority }; if (dueAt) body.due_at = new Date(dueAt).toISOString(); await apiJson("/api/tasks", { method: "POST", body }); setTitle(""); setDueAt(""); await load(); } catch (value) { setError(value.message); } }}><label>New task<input aria-label="New Task" required value={title} onChange={(event) => setTitle(event.target.value)} /></label><label>Priority<select aria-label="New Task Priority" value={priority} onChange={(event) => setPriority(event.target.value)}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select></label><label>Due at<input aria-label="New Task Due At" type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /></label><button type="submit">Create Task</button></form>
    {Object.entries(groups).map(([group, tasks]) => <section key={group}><h3>{group}</h3>{!tasks.length ? <p>No {group.toLowerCase()} tasks.</p> : <ul className="task-list">{tasks.map((task) => <li key={task.id}><div>{editingId === task.id ? <form className="inline-form" onSubmit={async (event) => { event.preventDefault(); try { await apiJson(`/api/tasks/${task.id}`, { method: "PATCH", body: { title: editingTitle, expected_revision: task.revision } }); setEditingId(""); await load(); } catch (value) { setError(value.message); } }}><label>Edit title<input aria-label={`Edit Task ${task.id}`} required value={editingTitle} onChange={(event) => setEditingTitle(event.target.value)} /></label><button type="submit">Save</button></form> : <strong>{task.title}</strong>}<span>{task.priority} priority{task.due_at ? ` · ${new Date(task.due_at).toLocaleString()}` : ""}</span>{task.application_id ? <Link to={`/applications/${task.application_id}`}>Open Application</Link> : null}</div><div className="button-row"><button onClick={() => { setEditingId(task.id); setEditingTitle(task.title); }}>Edit</button><button onClick={() => action(task, task.status === "completed" ? "reopen" : "complete")}>{task.status === "completed" ? "Reopen" : "Complete"}</button></div></li>)}</ul>}</section>)}
  </section>;
}
