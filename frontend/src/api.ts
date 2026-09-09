let token = sessionStorage.getItem("clinic-session") || "";
export function hasSession() { return Boolean(token); }
export function setToken(value: string) {
  token = value;
  if (value) sessionStorage.setItem("clinic-session", value);
  else sessionStorage.removeItem("clinic-session");
}
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (typeof options.body === "string")
    headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...options,
      headers,
      cache: "no-store",
      signal: options.signal ?? AbortSignal.timeout(180000),
    });
  } catch {
    throw new ApiError(
      0,
      "Cannot reach the clinic service. Check your connection and try again.",
    );
  }
  if (response.status === 401 && path !== "/auth/login") {
    setToken("");
    window.dispatchEvent(new Event("session-expired"));
  }
  const value =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      response.status,
      value?.error?.message ||
        value?.answer ||
        `Request failed (${response.status}).`,
    );
  return value;
}
export const send = (path: string, body: unknown, method = "POST") =>
  api(path, { method, body: JSON.stringify(body) });
// Decimal strings remain authoritative. Number conversion is used only for chart coordinates.
export function money(value: unknown, currency = "USD"): string {
  if (value === null || value === undefined) return "No data";
  const match = String(value).match(/^(-?)(\d+)(?:\.(\d+))?$/);
  if (!match) return String(value);
  const fraction = (match[3] || "").padEnd(3, "0");
  let cents = BigInt(match[2]) * 100n + BigInt(fraction.slice(0, 2));
  if (Number(fraction[2]) >= 5) cents++;
  const whole = (cents / 100n).toLocaleString("en-US");
  const symbol = currency === "USD" ? "$" : `${currency} `;
  return `${match[1]}${symbol}${whole}.${(cents % 100n).toString().padStart(2, "0")}`;
}
export function percent(value: unknown): string {
  if (value == null) return "No data";
  return `${money(value, "PCT").replace("PCT ", "")}%`;
}
