import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App } from "./main";
import { setToken } from "./api";

let metadata = { first_date: "2026-01-01", last_date: "2026-01-31", clinic_locations: [] };
vi.mock("./imports", () => ({ default: ({ onCompleted }: { onCompleted: (row: unknown) => void }) =>
  <button onClick={() => { metadata={...metadata,last_date:"2026-02-28"}; onCompleted({upload_id:"new-upload",status:"completed"}); }}>Complete test import</button> }));
vi.mock("./overview", () => ({ default: ({ start, end, dataVersion }: { start:string;end:string;dataVersion:number }) =>
  <div data-testid="report-range">{start} / {end} / {dataVersion}</div> }));

beforeEach(() => {
  metadata={first_date:"2026-01-01",last_date:"2026-01-31",clinic_locations:[]};
  setToken("synthetic-session"); window.location.hash=encodeURIComponent("Data imports");
  vi.stubGlobal("fetch",vi.fn(async (url:string) => ({ok:true,status:200,json:async()=>
    url.endsWith("/auth/me")?{username:"owner"}:url.endsWith("/analytics/metadata")?structuredClone(metadata):{enabled:true}})));
});
afterEach(()=>{cleanup();setToken("");window.location.hash="";vi.unstubAllGlobals();});

it("refreshes available dates after completion without reloading the browser",async()=>{
  render(<App/>);
  fireEvent.click(await screen.findByRole("button",{name:"Complete test import"}));
  await waitFor(()=>expect(vi.mocked(fetch).mock.calls.filter(c=>String(c[0]).endsWith('/analytics/metadata')).length).toBeGreaterThanOrEqual(2));
  fireEvent.click(screen.getByRole("button",{name:"Overview"}));
  await waitFor(()=>expect(screen.getByTestId("report-range").textContent).toBe("2026-01-01 / 2026-02-28 / 1"));
});

it("preserves intentionally narrowed dates across import completion",async()=>{
  render(<App/>);await screen.findByRole("button",{name:"Complete test import"});
  fireEvent.click(screen.getByRole("button",{name:"Overview"}));
  await screen.findByTestId("report-range");
  fireEvent.change(screen.getByLabelText("From"),{target:{value:"2026-01-10"}});
  fireEvent.click(screen.getByRole("button",{name:"Data imports"}));
  fireEvent.click(await screen.findByRole("button",{name:"Complete test import"}));
  await waitFor(()=>expect(vi.mocked(fetch).mock.calls.filter(c=>String(c[0]).endsWith('/analytics/metadata')).length).toBeGreaterThanOrEqual(2));
  fireEvent.click(screen.getByRole("button",{name:"Overview"}));
  await waitFor(()=>expect(screen.getByTestId("report-range").textContent).toBe("2026-01-10 / 2026-01-31 / 1"));
});
