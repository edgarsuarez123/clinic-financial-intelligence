import { afterEach, expect, it, vi } from "vitest";
import { newId } from "./uuid";

afterEach(() => vi.unstubAllGlobals());

it("creates valid version 4 IDs when randomUUID is unavailable on HTTP LAN origins", () => {
  const fill = vi.fn((bytes: Uint8Array) => bytes.fill(255));
  vi.stubGlobal("crypto", { getRandomValues: fill });
  expect(newId()).toBe("ffffffff-ffff-4fff-bfff-ffffffffffff");
  expect(fill).toHaveBeenCalledOnce();
});
