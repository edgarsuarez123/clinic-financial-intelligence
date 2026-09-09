import { expect, it } from "vitest";
import { financialCSV, sampleProfile, type ColumnProfile } from "./financial-csv";
it("selects dedicated sample mappings without guessing for unrelated exports", () => {
  expect(sampleProfile("staff-costs.csv")).toBe("staff-costs");
  expect(sampleProfile("Medical-Billing.csv")).toBe("medical-billing");
  expect(sampleProfile("other.csv")).toBeNull();
});
const profile: ColumnProfile = {
  columns: { date: "date", amount: "amount", type: "type", category: "category", provider: "provider", medical_insurance: "insurer", billing_code: "code" },
  delimiter: ",", date_format: "%Y-%m-%d",
  allowed_values: { type: ["revenue"], category: ["Collections"], provider: ["D1"], medical_insurance: ["Demo A"], billing_code: ["DEMO-001"] },
};
const header = "patient_name,date,amount,type,category,provider,insurer,code\r\n";
const row = '"Synthetic, Person",2026-01-05,0.10,revenue,Collections,D1,Demo A,DEMO-001\r\n';

it("removes patient columns locally and preserves every financial row and cent", () => {
  const result = financialCSV(header + row + row, profile);
  expect(result.excludedColumns).toBe(1);
  expect(result.rows).toBe(2);
  expect(result.csv).not.toContain("patient_name");
  expect(result.csv).not.toContain("Synthetic");
  expect(result.csv.match(/0.10/g)).toHaveLength(2);
  expect(result.csv).toContain('"Demo A","DEMO-001"');
});
it("ignores quoted multiline identifiers and produces the same payload when only identifiers change", () => {
  expect(financialCSV(header + row, profile).csv).toBe(
    financialCSV(header + row.replace('Synthetic, Person', 'Other\r\nPerson'), profile).csv);
});
it("rejects unmapped values without repeating potential identifiers", () => {
  let message = "";
  try { financialCSV(header + row.replace("Demo A", "PRIVATE NAME"), profile); }
  catch (e) { message = (e as Error).message; }
  expect(message).toContain("Nothing was uploaded");
  expect(message).not.toContain("PRIVATE");
});
it("rejects missing/duplicate headers, malformed quotes, invalid amounts and blank rows", () => {
  for (const text of [header.replace("patient_name", "date") + row,
    header.replace("insurer", "unknown") + row, header + row.replace("0.10", "1e2"),
    header + row.replace('"Synthetic, Person"', '"unclosed'), header + row + "\r\n"])
    expect(() => financialCSV(text, profile)).toThrow();
});
