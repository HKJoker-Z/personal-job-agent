import {
  apiFetch,
  apiJson,
  configureApiSecurity,
  normalizeApiError,
} from "./client";

describe("CSRF-aware API client", () => {
  beforeEach(() => {
    configureApiSecurity({ csrf: "", refreshSession: null, onUnauthorized: null });
  });

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

  it("recognizes the stable CSRF code without English substring matching", async () => {
    const refresh = vi.fn().mockResolvedValue("new");
    global.fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        error: {
          code: "CSRF_VALIDATION_FAILED",
          message: "Localized safe message.",
          request_id: "csrf-correlation",
          details: {},
        },
      }), { status: 403, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response("{}", { status: 200 }));
    configureApiSecurity({ csrf: "old", refreshSession: refresh });
    const response = await apiFetch("/api/analyze", {
      method: "POST",
      headers: { "Idempotency-Key": "12345678-1234-4123-8123-123456789abc" },
    });
    expect(response.ok).toBe(true);
    expect(refresh).toHaveBeenCalledOnce();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(new Headers(fetch.mock.calls[0][1].headers).get("Idempotency-Key"))
      .toBe("12345678-1234-4123-8123-123456789abc");
    expect(new Headers(fetch.mock.calls[1][1].headers).get("Idempotency-Key"))
      .toBe("12345678-1234-4123-8123-123456789abc");
  });

  it("normalizes the four-field Analyze error envelope", () => {
    expect(normalizeApiError({
      error: {
        code: "RESUME_SOURCE_INVALID",
        message: "Choose a valid resume.",
        request_id: "request-123",
        details: { field: "resume" },
      },
    })).toEqual({
      code: "RESUME_SOURCE_INVALID",
      message: "Choose a valid resume.",
      request_id: "request-123",
      details: { field: "resume" },
      stable: true,
    });
  });

  it("preserves the temporary legacy detail parser", () => {
    expect(normalizeApiError({ detail: "Legacy safe detail." })).toEqual({
      code: "",
      message: "Legacy safe detail.",
      request_id: "",
      details: {},
      stable: false,
    });
  });

  it("attaches stable error metadata without using details as the message", async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: {
        code: "ANALYZE_PERSISTENCE_FAILED",
        message: "The analysis could not be saved.",
        request_id: "support-123",
        details: { internal: "must-not-become-message" },
      },
    }), { status: 503, headers: { "Content-Type": "application/json" } }));
    await expect(apiJson("/api/analyze", { method: "POST" })).rejects.toMatchObject({
      message: "The analysis could not be saved.",
      apiError: {
        code: "ANALYZE_PERSISTENCE_FAILED",
        request_id: "support-123",
      },
    });
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
