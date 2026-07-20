import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "./LoginPage";
import { REMEMBERED_EMAIL_KEY } from "../auth/login-storage";

const login = vi.fn();
vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({ user: null, login, initialized: true }),
}));

function view() {
  return render(<MemoryRouter><LoginPage /></MemoryRouter>);
}

describe("Version 2.0.1 login", () => {
  beforeEach(() => {
    login.mockReset().mockResolvedValue({ authenticated: true });
    localStorage.clear();
  });

  it("exposes password-manager-compatible fields", () => {
    view();
    expect(screen.getByLabelText("Email")).toHaveAttribute("type", "email");
    expect(screen.getByLabelText("Email")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Email")).toHaveAttribute("inputmode", "email");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
  });

  it("submits remember_me and never stores a password", async () => {
    view();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: " User@Example.COM " } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "test-only-password" } });
    fireEvent.click(screen.getByLabelText("Remember me"));
    fireEvent.click(screen.getByLabelText("Remember email"));
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(login).toHaveBeenCalledWith("user@example.com", "test-only-password", true));
    expect(localStorage.getItem(REMEMBERED_EMAIL_KEY)).toBe("user@example.com");
    expect(JSON.stringify(localStorage)).not.toContain("test-only-password");
  });

  it("clears a remembered email immediately when disabled", () => {
    localStorage.setItem(REMEMBERED_EMAIL_KEY, "user@example.com");
    view();
    expect(screen.getByLabelText("Email")).toHaveValue("user@example.com");
    fireEvent.click(screen.getByLabelText("Remember email"));
    expect(localStorage.getItem(REMEMBERED_EMAIL_KEY)).toBeNull();
  });

  it("toggles password visibility accessibly", () => {
    view();
    const password = screen.getByLabelText("Password");
    expect(password).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "Hide password" })).toHaveAttribute("aria-pressed", "true");
  });

  it("prevents duplicate submission while login is pending", async () => {
    let resolve;
    login.mockReturnValue(new Promise((done) => { resolve = done; }));
    view();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "user@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "test-only-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByRole("button", { name: "Signing in…" })).toBeDisabled();
    fireEvent.submit(screen.getByRole("button", { name: "Signing in…" }).closest("form"));
    expect(login).toHaveBeenCalledTimes(1);
    resolve({ authenticated: true });
    await waitFor(() => expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled());
  });
});
