import { afterEach, it, expect, vi } from "vitest";
import { render, screen, waitFor, cleanup, fireEvent } from "@testing-library/react";
import { App } from "./main";
import { setToken } from "./api";

afterEach(() => { cleanup(); setToken(""); window.location.hash = ""; vi.unstubAllGlobals(); });
it("restores the authenticated page after remount and follows browser history", async () => {
  setToken("valid-session");
  window.location.hash = encodeURIComponent("Ask Clarity");
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({
    ok: true, status: 200, json: async () => url.endsWith("/auth/me") ? { username: "owner" } : { enabled: false },
  })));
  const view = render(<App />);
  expect(await screen.findByRole("heading", { name: "Ask Clarity" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Revenue explorer" }));
  await waitFor(() => expect(window.location.hash).toBe("#Revenue%20explorer"));
  view.unmount();
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Revenue explorer" })).toBeTruthy();
  window.location.hash = encodeURIComponent("Providers");
  window.dispatchEvent(new Event("hashchange"));
  expect(await screen.findByRole("heading", { name: "Providers" })).toBeTruthy();
});
