import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App } from "./main";
import { setToken } from "./api";

vi.mock("./clarity", () => ({ default: ({onDraft}: {onDraft: (draft: unknown)=>void}) =>
  <button onClick={()=>onDraft({name:"Private proposed payroll"})}>Propose plan</button> }));
vi.mock("./budgets", () => ({ default: ({draft}: {draft: {name:string}|null}) =>
  <div>{draft?.name || "No proposed plan"}</div> }));

afterEach(()=>{cleanup();setToken("");window.history.replaceState({},"","/");vi.unstubAllGlobals();});

it("clears a private proposed plan when the session expires before another account signs in", async()=>{
  setToken("owner-session");window.location.hash=encodeURIComponent("Ask Clarity");
  vi.stubGlobal("fetch", vi.fn(async(url:string)=>({ok:true,status:200,json:async()=>
    url.endsWith("/auth/me")?{username:"owner"}:url.endsWith("/auth/login")?{access_token:"manager-session"}:
    url.endsWith("/analytics/metadata")?{first_date:"2026-01-01",last_date:"2026-01-31"}:{enabled:true}})));
  render(<App/>);
  fireEvent.click(await screen.findByRole("button",{name:"Propose plan"}));
  expect(await screen.findByText("Private proposed payroll")).toBeTruthy();
  setToken("");window.dispatchEvent(new Event("session-expired"));
  await screen.findByRole("button",{name:"Sign in to your workspace"});
  fireEvent.change(screen.getByLabelText("Username"),{target:{value:"manager"}});
  fireEvent.change(screen.getByLabelText("Password"),{target:{value:"synthetic"}});
  fireEvent.click(screen.getByRole("button",{name:"Sign in to your workspace"}));
  await waitFor(()=>expect(screen.getByText("No proposed plan")).toBeTruthy());
  expect(screen.queryByText("Private proposed payroll")).toBeNull();
});
