import { apiFetch, apiJson, configureApiSecurity } from "./client";

describe("CSRF-aware API client", () => {
  it("adds CSRF to unsafe requests but never to GET", async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
    configureApiSecurity({ csrf: "memory-only-csrf" });
    await apiFetch("/safe");
    await apiFetch("/unsafe", { method: "POST" });
    expect(new Headers(fetch.mock.calls[0][1].headers).has("X-CSRF-Token")).toBe(false);
    expect(new Headers(fetch.mock.calls[1][1].headers).get("X-CSRF-Token")).toBe("memory-only-csrf");
  });

  it("calls the global unauthorized handler on 401", async () => {
    const unauthorized = vi.fn();
    global.fetch = vi.fn().mockResolvedValue(new Response("{}", { status: 401 }));
    configureApiSecurity({ csrf: "", onUnauthorized: unauthorized });
    await apiFetch("/protected");
    expect(unauthorized).toHaveBeenCalledOnce();
  });

  it("refreshes a rejected CSRF token once", async () => {
    const refresh = vi.fn().mockResolvedValue("new");
    global.fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "CSRF validation failed." }), { status: 403, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response("{}", { status: 200 }));
    configureApiSecurity({ csrf: "old", refreshSession: refresh });
    const response = await apiFetch("/unsafe", { method: "PATCH" });
    expect(response.ok).toBe(true);
    expect(refresh).toHaveBeenCalledOnce();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(new Headers(fetch.mock.calls[1][1].headers).get("X-CSRF-Token")).toBe("new");
  });

  it("maps 409 to a safe stale-update message", async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response("{}", { status: 409, headers: { "Content-Type": "application/json" } }));
    await expect(apiJson("/profile")).rejects.toThrow("changed elsewhere");
  });

  it("serializes JSON without persisting credentials", async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
    await apiJson("/profile", { method: "PUT", body: { headline: "Engineer" } });
    expect(fetch.mock.calls[0][1].body).toBe(JSON.stringify({ headline: "Engineer" }));
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});
