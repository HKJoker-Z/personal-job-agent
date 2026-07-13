import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./AuthProvider";
import { ProtectedRoute } from "./ProtectedRoute";

function Status() { const auth = useAuth(); return <div>{auth.user?.display_name || "anonymous"}<button onClick={() => auth.logout(true)}>Logout all</button></div>; }

describe("authentication bootstrap", () => {
  it("loads an authenticated Session into memory", async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ authenticated: true, user: { id: "u", display_name: "Admin", role: "admin" }, csrf_token: "csrf" }), { status: 200, headers: { "Content-Type": "application/json" } }));
    render(<AuthProvider><Status /></AuthProvider>);
    expect(await screen.findByText("Admin")).toBeInTheDocument();
    expect(localStorage.length).toBe(0);
  });

  it("redirects an unauthenticated protected route", async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ authenticated: false }), { status: 200, headers: { "Content-Type": "application/json" } }));
    render(<MemoryRouter initialEntries={["/profile"]}><AuthProvider><Routes><Route path="/login" element={<div>Login screen</div>} /><Route element={<ProtectedRoute />}><Route path="/profile" element={<div>Private profile</div>} /></Route></Routes></AuthProvider></MemoryRouter>);
    expect(await screen.findByText("Login screen")).toBeInTheDocument();
  });

  it("logout-all clears the in-memory user", async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ authenticated: true, user: { id: "u", display_name: "Admin", role: "admin" }, csrf_token: "csrf" }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ logged_out: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
    render(<AuthProvider><Status /></AuthProvider>);
    await screen.findByText("Admin"); fireEvent.click(screen.getByText("Logout all"));
    await waitFor(() => expect(screen.getByText("anonymous")).toBeInTheDocument());
  });
});
