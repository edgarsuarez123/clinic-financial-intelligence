import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import Imports from "./imports";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, api: apiMock };
});

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const config = {
  profiles: ["demo"],
  max_bytes: 10 * 1024 * 1024,
  clinic_locations: [],
  column_profiles: {
    demo: {
      columns: { date: "date", amount: "amount", type: "type", category: "category", provider: "provider" },
      delimiter: ",",
      date_format: "%Y-%m-%d",
      allowed_values: { type: ["revenue", "expense"], category: ["Collections"], provider: ["D1"] },
    },
  },
};

it("notifies once for an immediately completed duplicate and never while pending", async () => {
  const onCompleted = vi.fn();
  apiMock.mockResolvedValue({
    upload_id: "upload-1",
    status: "completed",
    duplicate: true,
    total_rows: 1,
    rows_accepted: 1,
    rows_rejected: 0,
  });
  const view = render(<Imports config={config} onCompleted={onCompleted} />);
  fireEvent.change(screen.getByRole("combobox", { name: "Column mapping profile" }), { target: { value: "demo" } });
  const input = view.container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, {
    target: {
      files: [new File([
        "patient_name,date,amount,type,category,provider\nPrivate Person,2026-01-05,10.00,revenue,Collections,D1\n",
      ], "export.csv")],
    },
  });
  await screen.findByText("Review financial column mapping");
  fireEvent.click(screen.getByRole("checkbox"));
  const submit = screen.getByRole("button", { name: "Validate & import" });
  await waitFor(() => expect((submit as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(submit);
  await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(onCompleted).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Refresh status" }));
  await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
  expect(onCompleted).toHaveBeenCalledTimes(1);
});

it("uploads only the projected financial CSV when the source contains identifiers", async () => {
  apiMock.mockResolvedValue({
    upload_id: "projected-upload",
    status: "pending",
    total_rows: 1,
    rows_accepted: 0,
    rows_rejected: 0,
  });
  const view = render(<Imports config={config} />);
  fireEvent.change(screen.getByRole("combobox", { name: "Column mapping profile" }), { target: { value: "demo" } });
  const input = view.container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, {
    target: {
      files: [new File([
        "patient_name,date,amount,type,category,provider\nPrivate Person,2026-01-05,10.00,revenue,Collections,D1\n",
      ], "export.csv")],
    },
  });
  await screen.findByText("Review financial column mapping");
  fireEvent.click(screen.getByRole("checkbox"));
  const submit = screen.getByRole("button", { name: "Validate & import" });
  await waitFor(() => expect((submit as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(submit);
  await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1));
  const body = apiMock.mock.calls[0][1].body as Blob;
  const uploaded = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(body);
  });
  expect(uploaded).not.toContain("Private Person");
  expect(uploaded).not.toContain("patient_name");
  expect(uploaded).toContain('"date","amount","type","category","provider"');
});

it("does not announce a pending upload", async () => {
  const onCompleted = vi.fn();
  apiMock.mockResolvedValue({ upload_id: "upload-2", status: "pending", total_rows: 1 });
  const view = render(<Imports config={config} onCompleted={onCompleted} />);
  fireEvent.change(screen.getByRole("combobox", { name: "Column mapping profile" }), { target: { value: "demo" } });
  const input = view.container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, {
    target: { files: [new File(["date,amount,type,category,provider\n2026-01-05,10.00,revenue,Collections,D1\n"], "export.csv")] },
  });
  await screen.findByText("Review financial column mapping");
  fireEvent.click(screen.getByRole("checkbox"));
  const submit = screen.getByRole("button", { name: "Validate & import" });
  await waitFor(() => expect((submit as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(submit);
  await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1));
  expect(onCompleted).not.toHaveBeenCalled();
});
