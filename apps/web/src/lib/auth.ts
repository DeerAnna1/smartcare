export const AUTH_STORAGE_KEY = "medhelp-auth";
export const AUTH_CHANGED_EVENT = "medhelp-auth-changed";
export const AUTH_COOKIE_KEY = "medhelp_token";

export interface StoredUser {
  user_id: string;
  username: string;
  display_name: string;
  avatar_url?: string;
  created_at: string;
}

export interface StoredAuth {
  token: string;
  user: StoredUser;
}

function isBrowser() {
  return typeof window !== "undefined";
}

export function getStoredAuth(): StoredAuth | null {
  if (!isBrowser()) {
    return null;
  }

  const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as StoredAuth;
  } catch {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
    return null;
  }
}

export function getStoredAuthToken(): string {
  return getStoredAuth()?.token ?? "";
}

export function setStoredAuth(auth: StoredAuth) {
  if (!isBrowser()) {
    return;
  }

  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(auth));
  document.cookie = `${AUTH_COOKIE_KEY}=${encodeURIComponent(auth.token)}; Path=/; Max-Age=${60 * 60 * 24 * 7}; SameSite=Lax`;
  window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
}

export function clearStoredAuth() {
  if (!isBrowser()) {
    return;
  }

  window.localStorage.removeItem(AUTH_STORAGE_KEY);
  document.cookie = `${AUTH_COOKIE_KEY}=; Path=/; Max-Age=0; SameSite=Lax`;
  window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
}
