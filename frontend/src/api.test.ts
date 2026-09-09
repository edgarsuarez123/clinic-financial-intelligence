import { afterEach, describe, it, expect, vi } from "vitest";
import { api, money, setToken } from "./api";
afterEach(() => {
  vi.unstubAllGlobals();
  setToken("");
});
describe("Exact financial formatting", () => {
  it("preserves large decimal values without binary conversion", () =>
    expect(money("9007199254740993.12")).toBe("$9,007,199,254,740,993.12"));
  it("rounds display only and distinguishes missing from zero", () => {
    expect(money("1.005")).toBe("$1.01");
    expect(money("0")).toBe("$0.00");
    expect(money(null)).toBe("No data");
  });
});
it("sends the session only to the same-origin API", async () => {
  const fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ ok: true }),
  });
  vi.stubGlobal("fetch", fetch);
  setToken("test-session");
  await api("/analytics/config");
  expect(fetch.mock.calls[0][0]).toBe("/api/v1/analytics/config");
  expect(fetch.mock.calls[0][1].headers.get("Authorization")).toBe(
    "Bearer test-session",
  );
});
it("clears expired sessions and exposes structured errors", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ error: { message: "Expired" } }),
    }),
  );
  const listener = vi.fn();
  window.addEventListener("session-expired", listener);
  await expect(api("/auth/me")).rejects.toThrow("Expired");
  expect(listener).toHaveBeenCalledOnce();
  window.removeEventListener("session-expired", listener);
});
