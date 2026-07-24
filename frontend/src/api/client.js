let csrfToken = "";
let sessionRefresher = null;
let unauthorizedHandler = null;
const MAX_SAFE_ERROR_MESSAGE = 500;

export function configureApiSecurity({ csrf, refreshSession, onUnauthorized }) {
  csrfToken = csrf || "";
  sessionRefresher = refreshSession || null;
  unauthorizedHandler = onUnauthorized || null;
}

function boundedMessage(value, fallback) {
  const message = typeof value === "string" ? value : "";
  return message && message.length <= MAX_SAFE_ERROR_MESSAGE ? message : fallback;
}

export function normalizeApiError(payload, fallback = "Request failed safely.") {
  const stable = payload?.error;
  if (stable && typeof stable === "object" && !Array.isArray(stable)) {
    return {
      code: typeof stable.code === "string" ? stable.code.slice(0, 80) : "",
      message: boundedMessage(stable.message, fallback),
      request_id: typeof stable.request_id === "string" ? stable.request_id.slice(0, 64) : "",
      details: stable.details && typeof stable.details === "object" && !Array.isArray(stable.details)
        ? stable.details
        : {},
      stable: true,
    };
  }
  const detail = payload?.detail;
  const legacyMessage = typeof detail === "string"
    ? detail
    : (detail && typeof detail === "object" ? detail.message : "");
  return {
    code: detail && typeof detail === "object" && typeof detail.error_code === "string"
      ? detail.error_code.slice(0, 80)
      : "",
    message: boundedMessage(legacyMessage, fallback),
    request_id: "",
    details: detail && typeof detail === "object" && !Array.isArray(detail) ? detail : {},
    stable: false,
  };
}

function safeMessage(status, payload) {
  const normalized = normalizeApiError(payload);
  if (normalized.stable) return normalized.message;
  if (status === 409) return "This record changed elsewhere. Reload before saving again.";
  const detail = payload?.detail;
  if ((status === 422 || status === 400 || status === 413) && typeof detail === "string" && detail.length < 240) return detail;
  if (status === 422 || status === 400 || status === 413) return "Some submitted fields are invalid.";
  if (status === 429) return "Too many attempts. Please wait and try again.";
  if (status === 403) return "This action is not permitted or its security token expired.";
  if (status === 401) return "Your Session has expired. Please sign in again.";
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
    const normalized = normalizeApiError(payload, "");
    if (
      normalized.code === "CSRF_VALIDATION_FAILED"
      || String(payload?.detail || "").includes("CSRF")
    ) {
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
    error.apiError = normalizeApiError(payload);
    error.payload = payload;
    throw error;
  }
  return payload;
}
