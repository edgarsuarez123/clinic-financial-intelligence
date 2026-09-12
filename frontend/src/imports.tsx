import { useEffect, useMemo, useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { ApiError, api } from "./api";
import { Card, Evidence, Field, Notice, Select, Table } from "./components";
import type { Row } from "./types";
import PDFImport from "./pdf-import";
import {
  csvHeaders,
  financialCSV,
  FinancialProjectionError,
  sampleProfile,
  type ColumnProfile,
} from "./financial-csv";
import "./import-workflow.css";

type UploadResult = Row;

class ImportValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ImportValidationError";
  }
}

type ImportsProps = {
  config: Row;
  onCompleted?: (upload: Row) => void;
};

const defaultableWholeFileFields = ["type", "category"];
const optionalSourceFields = ["provider", "medical_insurance", "billing_code"];

function kindFor(file: File | null): string {
  return file?.name.split(".").pop()?.toLowerCase() || "";
}

async function readTextFile(file: File): Promise<string> {
  const candidate = file as File & {
    arrayBuffer?: () => Promise<ArrayBuffer>;
    text?: () => Promise<string>;
  };
  if (typeof candidate.arrayBuffer === "function")
    return new TextDecoder("utf-8", { fatal: true }).decode(await candidate.arrayBuffer());
  if (typeof candidate.text === "function") return candidate.text();
  // Older test DOMs do not expose Blob.arrayBuffer/text. FileReader is also
  // available in the supported browsers and keeps the source local.
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        resolve(new TextDecoder("utf-8", { fatal: true }).decode(reader.result as ArrayBuffer));
      } catch (cause) {
        reject(cause);
      }
    };
    reader.onerror = () => reject(reader.error || Error("The file could not be read."));
    reader.readAsArrayBuffer(file);
  });
}

function profileNames(config: Row): string[] {
  if (Array.isArray(config.profiles)) return config.profiles.map(String);
  if (config.profiles && typeof config.profiles === "object") return Object.keys(config.profiles);
  return [];
}

function profileFor(config: Row, name: string): ColumnProfile | null {
  const candidate = config.column_profiles?.[name];
  if (!candidate || typeof candidate !== "object" || !candidate.columns) return null;
  return candidate as ColumnProfile;
}

function approvedValues(profile: ColumnProfile | null, key: string): string[] {
  const values = profile?.allowed_values?.[key];
  return Array.isArray(values) ? values.map(String) : [];
}

function initialSourceMapping(profile: ColumnProfile, headers: string[]): Record<string, string> {
  return Object.fromEntries(
    Object.entries(profile.columns).map(([key, label]) => [
      key,
      headers.includes(label) ? label : "",
    ]),
  );
}

function safeError(error: unknown, fallback: string): string {
  // Preserve only server errors that have already crossed the API's sanitized
  // error boundary. Local parser and browser errors are intentionally hidden
  // here so a future parser cannot reflect source cells in the UI.
  const message = error instanceof ApiError || error instanceof FinancialProjectionError || error instanceof ImportValidationError
    ? error.message
    : "";
  return message && message.length <= 300 && !/[\r\n\0]/.test(message) ? message : fallback;
}

function mappingReady(
  profile: ColumnProfile | null,
  headers: string[],
  mapping: Record<string, string>,
  defaults: Record<string, string>,
): boolean {
  if (!profile || !headers.length) return false;
  return Object.keys(profile.columns).every((key) => {
    if (mapping[key]) return true;
    if (defaultableWholeFileFields.includes(key)) return Boolean(defaults[key]);
    // Provider and revenue dimensions may be absent. They are projected as a
    // safe blank, never inferred from another field.
    if (optionalSourceFields.includes(key)) return true;
    return false;
  });
}

function mappingOptions(
  profile: ColumnProfile,
  key: string,
  headers: string[],
): (string | [string, string])[] {
  const canBeAbsent = defaultableWholeFileFields.includes(key) || optionalSourceFields.includes(key);
  return [
    ["", canBeAbsent ? "Not present in this export" : "Select a source column"],
    ...headers.map((header) => [header, header] as [string, string]),
  ];
}

function wholeFileOptions(profile: ColumnProfile, key: string): (string | [string, string])[] {
  return [
    ["", `Choose an approved ${key}`],
    ...approvedValues(profile, key).map((value) => [value, value] as [string, string]),
  ];
}

/**
 * Financial import workflow. The source file is read and projected in this
 * browser; only the profile-shaped financial CSV is sent to the API.
 */
export default function Imports({ config, onCompleted }: ImportsProps) {
  const [clinic, setClinic] = useState("");
  const [preparedPDF, setPreparedPDF] = useState<Blob | null>(null);
  const [financialOnly, setFinancialOnly] = useState(false);
  const [projection, setProjection] = useState("");
  const [profile, setProfile] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [lookup, setLookup] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sourceHeaders, setSourceHeaders] = useState<string[]>([]);
  const [sourceMapping, setSourceMapping] = useState<Record<string, string>>({});
  const [wholeFileDefaults, setWholeFileDefaults] = useState<Record<string, string>>({});
  const [mappingError, setMappingError] = useState("");
  const [pollTick, setPollTick] = useState(0);
  const completedUploadIds = useRef<Set<string>>(new Set());
  const onCompletedRef = useRef(onCompleted);
  const headerGeneration = useRef(0);
  const pollRequest = useRef(0);

  useEffect(() => {
    onCompletedRef.current = onCompleted;
  }, [onCompleted]);

  const selectedProfile = useMemo(
    () => profileFor(config, profile),
    [config, profile],
  );
  const kind = kindFor(file);
  const isCSV = kind === "csv";
  const isPDF = kind === "pdf";
  const names = profileNames(config);

  useEffect(() => {
    setFinancialOnly(false);
    setProjection("");
    setPreparedPDF(null);
    setSourceHeaders([]);
    setSourceMapping({});
    setWholeFileDefaults({});
    setMappingError("");
    headerGeneration.current += 1;
  }, [file, profile]);

  useEffect(() => {
    if (!file || !isCSV || !selectedProfile) return;
    const generation = ++headerGeneration.current;
    let active = true;
    (async () => {
      try {
        const text = await readTextFile(file);
        const headers = csvHeaders(text, selectedProfile.delimiter);
        if (!active || generation !== headerGeneration.current) return;
        setSourceHeaders(headers);
        setSourceMapping(initialSourceMapping(selectedProfile, headers));
        setWholeFileDefaults({});
        setMappingError("");
      } catch (cause) {
        if (!active || generation !== headerGeneration.current) return;
        setSourceHeaders([]);
        setSourceMapping({});
        setMappingError(safeError(cause, "The CSV headers could not be read. Nothing was uploaded."));
      }
    })();
    return () => {
      active = false;
    };
  }, [file, isCSV, selectedProfile]);

  // A completed response can be returned immediately by a duplicate upload,
  // so this check intentionally does not require `duplicate` to be true.
  useEffect(() => {
    const completed = result;
    const uploadId = completed?.upload_id == null ? "" : String(completed.upload_id);
    if (!completed || !uploadId || String(completed.status || "").toLowerCase() !== "completed") return;
    if (completedUploadIds.current.has(uploadId)) return;
    completedUploadIds.current.add(uploadId);
    onCompletedRef.current?.(completed);
  }, [result]);

  useEffect(() => {
    const uploadId = result?.upload_id == null ? "" : String(result.upload_id);
    const status = String(result?.status || "").toLowerCase();
    if (!uploadId || !["queued", "processing", "pending"].includes(status)) return;
    const request = ++pollRequest.current;
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const next = await api<UploadResult | null>(`/uploads/${encodeURIComponent(uploadId)}`);
        if (active && request === pollRequest.current && next) setResult(next);
      } catch (cause) {
        if (active && request === pollRequest.current)
          setError(safeError(cause, "The upload status could not be refreshed."));
      } finally {
        // Keep polling while the server reports a pending state, including
        // when a transient status request failed.
        if (active && request === pollRequest.current) setPollTick((tick) => tick + 1);
      }
    }, 2000);
    return () => {
      active = false;
      window.clearTimeout(timer);
      if (pollRequest.current === request) pollRequest.current += 1;
    };
  }, [result?.upload_id, result?.status, pollTick]);

  async function run(action: () => Promise<UploadResult>) {
    const request = ++pollRequest.current;
    setBusy(true);
    setError("");
    try {
      const next = await action();
      if (request === pollRequest.current) setResult(next);
    } catch (cause) {
      if (request === pollRequest.current)
        setError(safeError(cause, "The import could not be completed. Nothing was uploaded."));
    } finally {
      if (request === pollRequest.current) setBusy(false);
    }
  }

  const readyForCSV = mappingReady(selectedProfile, sourceHeaders, sourceMapping, wholeFileDefaults);
  const clinicLocations = Array.isArray(config.clinic_locations) ? config.clinic_locations : [];
  const maxBytes = Number(config.max_bytes) || 10 * 1024 * 1024;
  const profileColumnKeys = selectedProfile ? Object.keys(selectedProfile.columns) : [];

  function changeSource(key: string, value: string) {
    setSourceMapping((current) => ({ ...current, [key]: value }));
    if (defaultableWholeFileFields.includes(key) && value)
      setWholeFileDefaults((current) => ({ ...current, [key]: "" }));
    setMappingError("");
  }

  function changeDefault(key: string, value: string) {
    setWholeFileDefaults((current) => ({ ...current, [key]: value }));
    if (value) setSourceMapping((current) => ({ ...current, [key]: "" }));
    setMappingError("");
  }

  return (
    <>
      <div className="two-col import-workflow">
        <Card title="Import financial data">
          {clinicLocations.length > 0 && (
            <Select
              label="Clinic location for this file"
              value={clinic}
              onChange={setClinic}
              options={[["", "Select a clinic"], ...clinicLocations]}
            />
          )}
          <p>CSV, XLSX, or a computer-generated text PDF. Up to 10 MiB.</p>
          <Select
            label="Column mapping profile"
            value={profile}
            onChange={setProfile}
            options={[["", "Select a mapping profile"], ...names]}
          />
          <label className="dropzone">
            <UploadCloud size={36} />
            <strong>{file?.name || "Choose a financial export"}</strong>
            <span>Browse CSV, XLSX, or PDF files</span>
            <input
              type="file"
              accept=".csv,.xlsx,.pdf"
              onChange={(event) => {
                const selected = event.target.files?.[0] || null;
                setFile(selected);
                setResult(null);
                setError("");
                const suggested = selected && sampleProfile(selected.name);
                if (suggested) {
                  setProfile(names.includes(suggested) ? suggested : "");
                  if (!names.includes(suggested))
                    setError(`The ${suggested} mapping is not installed. Nothing was uploaded.`);
                }
              }}
            />
          </label>
          <p className="fine">
            Source columns are mapped locally before validation. Only approved
            financial columns are sent; names, identifiers and other source
            values are discarded in this browser and are never previewed or uploaded.
          </p>

          {isCSV && selectedProfile && sourceHeaders.length > 0 && (
            <Card title="Review financial column mapping">
              <p className="fine">
                Map mixed documents row by row. If the export has no transaction
                type or category column, choose an approved whole-file value;
                the importer never infers either value from signs, names or codes.
              </p>
              <div className="import-mapping-list">
                {profileColumnKeys.map((key) => (
                  <div className="import-mapping-row" key={key}>
                    <Select
                      label={`${key.replaceAll("_", " ")} source column`}
                      value={sourceMapping[key] || ""}
                      options={mappingOptions(selectedProfile, key, sourceHeaders)}
                      onChange={(value) => changeSource(key, value)}
                    />
                    {defaultableWholeFileFields.includes(key) && !sourceMapping[key] && (
                      <Select
                        label={`Whole-file ${key.replaceAll("_", " ")}`}
                        value={wholeFileDefaults[key] || ""}
                        options={wholeFileOptions(selectedProfile, key)}
                        onChange={(value) => changeDefault(key, value)}
                      />
                    )}
                  </div>
                ))}
              </div>
              {!readyForCSV && (
                <p className="fine" role="status">
                  Map the date and amount columns, then map each row’s type and
                  category or choose an approved whole-file value.
                </p>
              )}
            </Card>
          )}
          {isCSV && mappingError && <Notice error>{mappingError}</Notice>}
          {isPDF && file && selectedProfile && (
            <PDFImport
              key={`${profile}:${file?.name}:${file?.lastModified}`}
              file={file}
              profile={selectedProfile}
              onPrepared={setPreparedPDF}
            />
          )}
          {preparedPDF && <Notice>Financial PDF rows confirmed. Select Validate &amp; import to submit.</Notice>}
          <label className="check">
            <input
              type="checkbox"
              checked={financialOnly}
              onChange={(event) => setFinancialOnly(event.target.checked)}
            />
            My approved financial columns contain no patient identifiers. For XLSX, the entire file is financial-only.
          </label>
          <button
            className="primary"
            disabled={
              busy || !file || !profile || !financialOnly ||
              (clinicLocations.length > 0 && !clinic) ||
              (isPDF && !preparedPDF) ||
              (isCSV && !readyForCSV) ||
              (isCSV && Boolean(mappingError))
            }
            onClick={() =>
              run(async () => {
                if (!file) throw new ImportValidationError("Choose a file before importing.");
                if (!selectedProfile) throw new ImportValidationError("Reload the app to load the approved financial mapping.");
                if (file.size > maxBytes) throw new ImportValidationError("File exceeds the 10 MiB limit.");
                let body: Blob = file;
                let uploadKind = kind;
                if (isPDF) {
                  if (!preparedPDF) throw new ImportValidationError("Extract and confirm the PDF financial rows first.");
                  body = preparedPDF;
                  uploadKind = "csv";
                } else if (isCSV) {
                  let text: string;
                  try {
                    text = await readTextFile(file);
                  } catch {
                    throw new ImportValidationError("CSV must be UTF-8. Nothing was uploaded.");
                  }
                  const clean = financialCSV(text, selectedProfile, {
                    sourceColumns: sourceMapping,
                    defaults: wholeFileDefaults,
                  });
                  if (clean.projected) body = new Blob([clean.csv], { type: "text/csv" });
                  setProjection(
                    `${clean.excludedColumns} source columns discarded locally; ${clean.rows} financial rows prepared.`,
                  );
                }
                if (!["csv", "xlsx", "pdf"].includes(uploadKind))
                  throw new ImportValidationError("Use a CSV, XLSX, or text PDF export. Nothing was uploaded.");
                return api(
                  `/uploads/${uploadKind}?profile=${encodeURIComponent(profile)}${clinic ? `&clinic_location=${encodeURIComponent(clinic)}` : ""}`,
                  {
                    method: "POST",
                    body,
                    headers: { "Content-Type": "application/octet-stream" },
                  },
                );
              })
            }
          >
            {busy ? "Submitting…" : "Validate & import"}
          </button>
          {projection && <p role="status">{projection}</p>}
        </Card>
        <Card title="A clean foundation">
          <ol className="steps">
            <li>
              <b>Use financial-only data</b>
              <p>Source identifiers stay local and are removed before the request.</p>
            </li>
            <li>
              <b>Choose the matching format</b>
              <p>Mapping profiles and approved values are configured by your administrator.</p>
            </li>
            <li>
              <b>Review every result</b>
              <p>Rejected rows include safe reasons. Identical files do not create duplicate transactions.</p>
            </li>
          </ol>
          <p className="fine">Different files with overlapping transactions still need review. Scanned PDFs are unsupported.</p>
        </Card>
      </div>
      {error && <Notice error>{error}</Notice>}
      <Card title="Import status">
        <div className="inline">
          <Field label="Reopen an upload by ID" value={lookup} onChange={setLookup} />
          <button disabled={busy || !lookup} onClick={() => run(() => api(`/uploads/${encodeURIComponent(lookup)}`))}>
            Look up
          </button>
        </div>
        {result && (
          <>
            <Notice>
              {result.duplicate ? "This file was already submitted. " : ""}
              Status: {result.status} · Upload ID: {result.upload_id}
            </Notice>
            <Table rows={[result]} columns={["total_rows", "rows_accepted", "rows_rejected", "status"]} />
            <Evidence value={result} label="Full import summary and rejection reasons" />
            <button disabled={busy} onClick={() => run(() => api(`/uploads/${result.upload_id}`))}>Refresh status</button>
            {String(result.status || "").toLowerCase() === "failed" && (
              <button
                disabled={busy}
                onClick={() => run(() => api(`/uploads/${result.upload_id}/retry`, {method: "POST"}))}
              >
                Retry import
              </button>
            )}
          </>
        )}
      </Card>
    </>
  );
}

export { Imports };
