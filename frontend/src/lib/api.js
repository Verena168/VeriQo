const BASE = "/api/v1";
const TOKEN_KEY = "veriqo_token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session lasts until reload */
  }
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function describe(detail) {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc: [...], msg}]
    return detail.map((d) => `${d.loc?.slice(1).join(".") || "input"}: ${d.msg.replace(/^Value error, /, "")}`).join("; ");
  }
  return detail.message || JSON.stringify(detail);
}

export async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(BASE + path, { method, headers, body: payload });
  } catch {
    throw new ApiError("Cannot reach the VERIQO API. Is the backend running on port 8000?", 0);
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && token) {
      setToken(null);
      window.dispatchEvent(new Event("veriqo:logout"));
    }
    throw new ApiError(describe(data?.detail) || `Request failed (${res.status})`, res.status);
  }
  return data;
}
