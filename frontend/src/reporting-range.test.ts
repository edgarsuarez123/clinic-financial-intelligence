import { expect, it } from "vitest";
import { refreshedRange } from "./reporting-range";

it("extends the full available reporting range after a completed import", () => {
  const old = { start: "2026-01-01", end: "2026-01-31" };
  const next = { start: "2025-12-01", end: "2026-02-28" };
  expect(refreshedRange(old, old, next)).toEqual(next);
});
it("preserves a user's narrowed selection", () => {
  const selected = { start: "2026-01-05", end: "2026-01-20" };
  expect(refreshedRange(selected, { start: "2026-01-01", end: "2026-01-31" }, { start: "2025-12-01", end: "2026-02-28" })).toEqual(selected);
});
