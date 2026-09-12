import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import Appointments from "./appointments";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, api: apiMock };
});
vi.mock("./plots", () => ({ default: () => <div>Chart</div> }));

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const config = {
  read_enabled: true,
  can_import: true,
  currency: "EUR",
  clinic_locations: ["North", "South"],
  category_labels: { new_patient: "New patient", follow_up: "Follow-up" },
  category_mappings: { "New visits": "new_patient" },
};
const metadata = {
  first_date: "2026-09-01",
  last_date: "2026-09-09",
  clinic_locations: ["North", "South"],
  categories: ["new_patient", "follow_up"],
};
const report = {
  summary: {
    observed: true,
    appointment_count: 5,
    billed_amount: "100.00",
    collected_amount: "80.00",
    average_billed_amount: "20.00",
    average_collected_amount: "16.00",
    billed_coverage: { known_rows: 1, total_rows: 1, complete: true },
    collected_coverage: { known_rows: 1, total_rows: 1, complete: true },
  },
  periods: [{ period_start: "2026-09-07", period_end: "2026-09-13", observed: true, appointment_count: 5 }],
  categories: [{ category: "new_patient", label: "New patient", appointment_count: 5, row_count: 1, billed_coverage: { known_rows: 1, total_rows: 1 } }],
  locations: [{ clinic_location: "North", appointment_count: 5 }],
  comparison: { appointment_count: null, change: null, change_pct: null, status: "partial_or_unavailable" },
};

function setupApi(overrides: (path: string, options?: RequestInit) => unknown = () => undefined) {
  apiMock.mockImplementation(async (path: string, options?: RequestInit) => {
    const custom = overrides(path, options);
    if (custom !== undefined) return custom;
    if (path === "/appointments/config") return config;
    if (path === "/appointments/metadata") return metadata;
    if (path.startsWith("/appointments/report?")) return report;
    throw new Error(`Unexpected API path: ${path}`);
  });
}

it("refetches the report when the clinic and category filters change", async () => {
  setupApi();
  render(<Appointments />);
  await screen.findByRole("heading", { name: "Category totals" });
  const reportCalls = () => apiMock.mock.calls.filter(([path]) => String(path).startsWith("/appointments/report?"));

  fireEvent.change(screen.getByRole("combobox", { name: "Clinic location" }), { target: { value: "North" } });
  await waitFor(() => expect(reportCalls().at(-1)?.[0]).toContain("clinic_location=North"));
  fireEvent.change(screen.getByRole("combobox", { name: "Appointment category" }), { target: { value: "new_patient" } });
  await waitFor(() => expect(reportCalls().at(-1)?.[0]).toContain("category=new_patient"));
});

it("rejects an unknown CSV header before making an import request", async () => {
  setupApi();
  const view = render(<Appointments />);
  await screen.findByRole("heading", { name: "Approved aggregate imports" });
  const input = screen.getByLabelText("Appointment CSV");
  fireEvent.change(input, {
    target: {
      files: [new File([
        "date,clinic_location,category,appointment_count,billed_amount,collected_amount,patient_name\n2026-09-01,North,new_patient,1,10.00,8.00,Private Person\n",
      ], "appointments.csv")],
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "Validate & import" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/headers must be exactly/i);
  expect(apiMock.mock.calls.some(([path]) => path === "/appointments/imports")).toBe(false);
});

it("polls a pending import once until duplicate completion, then refreshes metadata and report", async () => {
  const previousId = "a1111111-1111-4111-8111-111111111111";
  let pollCount = 0;
  let metadataCalls = 0;
  setupApi((path) => {
    if (path === "/appointments/metadata") {
      metadataCalls += 1;
      return metadata;
    }
    if (path === "/appointments/imports") return { upload_id: "upload-1", status: "pending", total_rows: 1 };
    if (path === "/appointments/imports/upload-1") {
      pollCount += 1;
      return { upload_id: "upload-1", status: "completed", duplicate: true, total_rows: 1, rows_accepted: 1, rows_rejected: 0 };
    }
    return undefined;
  });
  const view = render(<Appointments />);
  await screen.findByRole("heading", { name: "Approved aggregate imports" });
  fireEvent.change(screen.getByLabelText("Previous upload ID (optional)"), {target:{value:previousId}});
  fireEvent.change(screen.getByLabelText("Appointment CSV"), {
    target: {
      files: [new File([
        "date,clinic_location,category,appointment_count,billed_amount,collected_amount\n2026-09-01,North,New visits,1,10.00,8.00\n",
      ], "appointments.csv")],
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "Validate & import" }));
  await waitFor(() => expect(apiMock.mock.calls.some(([path]) => path === "/appointments/imports")).toBe(true));
  const submitted = apiMock.mock.calls.find(([path]) => path === "/appointments/imports");
  expect(JSON.parse(submitted![1].body).replace_upload_id).toBe(previousId);
  await screen.findByText("Appointment import completed.", {}, { timeout: 4000 });
  await new Promise((resolve) => window.setTimeout(resolve, 1300));
  expect(pollCount).toBe(1);
  expect(metadataCalls).toBeGreaterThanOrEqual(2);
  expect(apiMock.mock.calls.filter(([path]) => String(path).startsWith("/appointments/report?")).length).toBeGreaterThan(1);
  expect(view.container.textContent).toContain("EUR 100.00");
});
