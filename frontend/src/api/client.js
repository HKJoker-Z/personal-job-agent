let csrfToken = "";
let sessionRefresher = null;
let unauthorizedHandler = null;

export function configureApiSecurity({ csrf, refreshSession, onUnauthorized }) {
  csrfToken = csrf || "";
  sessionRefresher = refreshSession || null;
  unauthorizedHandler = onUnauthorized || null;
}

function safeMessage(status, payload) {
  if (status === 409) return "This record changed elsewhere. Reload before saving again.";
  if (status === 422 || status === 400) return "Some submitted fields are invalid.";
  if (status === 429) return "Too many attempts. Please wait and try again.";
  if (status === 403) return "This action is not permitted or its security token expired.";
  if (status === 401) return "Your Session has expired. Please sign in again.";
  const detail = payload?.detail;
  return typeof detail === "string" && detail.length < 240 ? detail : "Request failed safely.";
}

export async function apiFetch(input, init = {}, allowCsrfRetry = true) {
  const method = String(init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers || {});
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(input, { ...init, headers, credentials: "same-origin" });
  if (response.status === 401) unauthorizedHandler?.();
  if (response.status === 403 && allowCsrfRetry && sessionRefresher) {
    const payload = await response.clone().json().catch(() => ({}));
    if (String(payload?.detail || "").includes("CSRF")) {
      const refreshed = await sessionRefresher();
      if (typeof refreshed === "string") csrfToken = refreshed;
      if (refreshed) return apiFetch(input, init, false);
    }
  }
  return response;
}

export async function apiJson(input, init = {}) {
  const options = { ...init };
  if (options.body && typeof options.body !== "string" && !(options.body instanceof FormData)) {
    options.body = JSON.stringify(options.body);
    options.headers = { ...(options.headers || {}), "Content-Type": "application/json" };
  }
  const response = await apiFetch(input, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(safeMessage(response.status, payload));
    error.status = response.status;
    throw error;
  }
  return payload;
}
