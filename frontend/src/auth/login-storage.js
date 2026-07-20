export const REMEMBERED_EMAIL_KEY = "pja.v2.login.rememberedEmail";
export const MAX_EMAIL_LENGTH = 320;

export function normalizeRememberedEmail(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized || normalized.length > MAX_EMAIL_LENGTH) return "";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)) return "";
  return normalized;
}

export function loadRememberedEmail(storage = window.localStorage) {
  try {
    const normalized = normalizeRememberedEmail(storage.getItem(REMEMBERED_EMAIL_KEY));
    if (!normalized) storage.removeItem(REMEMBERED_EMAIL_KEY);
    return normalized;
  } catch {
    return "";
  }
}

export function saveRememberedEmail(value, storage = window.localStorage) {
  const normalized = normalizeRememberedEmail(value);
  try {
    if (!normalized) {
      storage.removeItem(REMEMBERED_EMAIL_KEY);
      return "";
    }
    storage.setItem(REMEMBERED_EMAIL_KEY, normalized);
    return normalized;
  } catch {
    return "";
  }
}

export function clearRememberedEmail(storage = window.localStorage) {
  try {
    storage.removeItem(REMEMBERED_EMAIL_KEY);
  } catch {
    // Storage can be unavailable in hardened/private browser contexts.
  }
}
