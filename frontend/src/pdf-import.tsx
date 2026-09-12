import { useEffect, useRef, useState } from "react";
import { Card, Field, Notice, Select, Table } from "./components";
import { sumDecimals } from "./cost-trends";
import type { ColumnProfile } from "./financial-csv";
import { financialPDF, type PDFLayout } from "./financial-pdf";

type PreparedRows = {
  csv: string;
  rows: number;
  records: Record<string, string>[];
};

type PDFImportProps = {
  file: File;
  profile: ColumnProfile;
  onPrepared: (body: Blob | null) => void;
};

const constantFields = new Set(["type", "category", "provider", "medical_insurance"]);

function initialLayout(profile: ColumnProfile): PDFLayout {
  return {
    firstPage: 1,
    lastPage: 1,
    top: 20,
    bottom: 90,
    columns: Object.fromEntries(
      Object.keys(profile.columns).map((key) => [
        key,
        {
          left: 0,
          right: 10,
          constant: "",
          useConstant: constantFields.has(key),
        },
      ]),
    ),
  };
}

export default function PDFImport({ file, profile, onPrepared }: PDFImportProps) {
  const [layout, setLayout] = useState<PDFLayout>(() => initialLayout(profile));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [clean, setClean] = useState<PreparedRows | null>(null);
  const [expected, setExpected] = useState("");
  const generation = useRef(0);

  // A preview is tied to the exact file, profile and layout that produced it.
  // Clearing both the rows and expected total prevents a confirmed old layout
  // from becoming valid again after an edit.
  useEffect(() => {
    generation.current += 1;
    setClean(null);
    setExpected("");
    setError("");
    // A layout/file change invalidates an in-flight extraction. Allow the user
    // to start the replacement extraction without waiting for the stale one.
    setBusy(false);
    onPrepared(null);
  }, [layout, file, profile, onPrepared]);

  const total = clean ? sumDecimals(clean.records.map((row) => row.amount)) : "0";
  const reconciled =
    /^-?\d+(?:\.\d{1,2})?$/.test(expected) &&
    /^-?0(?:\.0+)?$/.test(
      sumDecimals([
        total,
        expected.startsWith("-") ? expected.slice(1) : `-${expected}`,
      ]),
    );

  function updateColumn(key: string, update: Partial<PDFLayout["columns"][string]>) {
    setLayout((current) => ({
      ...current,
      columns: {
        ...current.columns,
        [key]: { ...current.columns[key], ...update },
      },
    }));
  }

  async function extract() {
    const request = ++generation.current;
    setBusy(true);
    setError("");
    setClean(null);
    setExpected("");
    onPrepared(null);
    try {
      const result = await financialPDF(file, profile, layout);
      if (request === generation.current) setClean(result);
    } catch {
      if (request === generation.current)
        setError(
          "The selected layout could not produce valid financial rows. Check page range, row area, column boundaries, dates and approved codes. Nothing was uploaded.",
        );
    } finally {
      if (request === generation.current) setBusy(false);
    }
  }

  function downloadCSV() {
    if (!clean) return;
    const urlFactory = URL as typeof URL & {
      createObjectURL?: (value: Blob) => string;
      revokeObjectURL?: (value: string) => void;
    };
    if (!urlFactory.createObjectURL) return;
    const url = urlFactory.createObjectURL(new Blob([clean.csv], { type: "text/csv" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${file.name.replace(/\.pdf$/i, "") || "financial"}-financial.csv`;
    anchor.click();
    window.setTimeout(() => urlFactory.revokeObjectURL?.(url), 0);
  }

  return (
    <Card title="Insurance payment statement layout">
      <p>
        Select the detail rows containing actual insurer payments, excluding headings,
        subtotals and totals. Positions are percentages measured from the page’s
        top-left corner. Use the same layout only on pages with the same table structure.
      </p>
      <p className="fine">
        Map paid amounts, not billed charges, allowed amounts or patient responsibility.
        No patient names, claim IDs or account numbers may be mapped. Original PDF bytes
        stay in this browser.
      </p>
      <div className="form-grid">
        {(["firstPage", "lastPage", "top", "bottom"] as const).map((key) => (
          <Field
            key={key}
            label={{
              firstPage: "First page",
              lastPage: "Last page",
              top: "Table top (%)",
              bottom: "Table bottom (%)",
            }[key]}
            type="number"
            value={layout[key]}
            onChange={(value) => setLayout((current) => ({ ...current, [key]: Number(value) }))}
          />
        ))}
      </div>
      {Object.keys(profile.columns).map((key) => {
        const column = layout.columns[key];
        const values = profile.allowed_values?.[key] || [];
        return (
          <div className="editor-row" key={key}>
            <h3>{key.replaceAll("_", " ")}</h3>
            <div className="form-grid">
              <Select
                label={`${key} source`}
                value={column.useConstant ? "constant" : "column"}
                options={
                  key === "amount" || key === "billing_code"
                    ? [["column", "PDF column"]]
                    : [
                        ["column", "PDF column"],
                        ["constant", "Same value for selected rows"],
                      ]
                }
                onChange={(value) => updateColumn(key, { useConstant: value === "constant" })}
              />
              {column.useConstant ? (
                key === "date" ? (
                  <Field
                    label="Statement payment date"
                    value={column.constant}
                    onChange={(value) => updateColumn(key, { constant: value })}
                  />
                ) : (
                  <Select
                    label={`${key} value`}
                    value={column.constant}
                    options={[
                      ["", key === "provider" ? "No provider" : "Choose an approved value"],
                      ...values.map((value) => [value, value] as [string, string]),
                    ]}
                    onChange={(value) => updateColumn(key, { constant: value })}
                  />
                )
              ) : (
                (["left", "right"] as const).map((edge) => (
                  <Field
                    key={edge}
                    label={`${key} ${edge} (%)`}
                    type="number"
                    value={column[edge]}
                    onChange={(value) => updateColumn(key, { [edge]: Number(value) })}
                  />
                ))
              )}
            </div>
          </div>
        );
      })}
      <button type="button" disabled={busy} onClick={() => void extract()}>
        {busy ? "Reading locally…" : "Extract financial rows locally"}
      </button>
      {error && <Notice error>{error}</Notice>}
      {clean && (
        <>
          <Notice>
            {clean.rows} financial rows extracted. Review the financial-only CSV before
            confirming. Check that its sum matches the insurer’s payment total and that
            no payment rows were omitted.
          </Notice>
          <p>
            <strong>Extracted paid total: {total}</strong> · Showing up to 100 rows below.
          </p>
          <Table rows={clean.records.slice(0, 100)} />
          <details>
            <summary>All extracted rows (CSV)</summary>
            <textarea
              aria-label="Extracted financial CSV"
              readOnly
              value={clean.csv}
              rows={10}
              style={{ width: "100%" }}
            />
          </details>
          <button type="button" onClick={downloadCSV}>Download financial-only CSV</button>
          <Field
            label="Expected paid total for selected rows"
            value={expected}
            onChange={(value) => {
              setExpected(value);
              onPrepared(null);
            }}
          />
          {!reconciled && (
            <p>Enter the payment total from your statement to reconcile the selected rows before confirming.</p>
          )}
          <button
            type="button"
            disabled={!reconciled}
            onClick={() => onPrepared(new Blob([clean.csv], { type: "text/csv" }))}
          >
            Confirm extracted rows for import
          </button>
        </>
      )}
    </Card>
  );
}
