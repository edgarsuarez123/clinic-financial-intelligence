// Local-only projection: no network, persistence, logging, or raw-cell errors.
export type ColumnProfile = {
  columns: Record<string, string>;
  delimiter: string;
  date_format: string;
  allowed_values: Record<string, string[]>;
  /**
   * The API deliberately exposes only approved values to the browser.  This
   * optional flag is accepted when a richer local profile is supplied, but is
   * not required by the existing ingestion config response.
   */
  allow_negative_amounts?: boolean;
};

export type FinancialCSVOptions = {
  /** Source header for each canonical financial field. */
  sourceColumns?: Partial<Record<string, string | null>>;
  /** Whole-document values used only when the corresponding source column is absent. */
  defaults?: Partial<Record<string, string>>;
};

type CSVColumn = { key: string; label: string };

/** Errors from the local projection layer contain only fixed field labels. */
export class FinancialProjectionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FinancialProjectionError";
  }
}

export function sampleProfile(filename: string): string | null {
  const name = filename.toLowerCase();
  return name === "staff-costs.csv" ? "staff-costs" :
    name === "medical-billing.csv" ? "medical-billing" : null;
}

function parseCSV(text: string, delimiter: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], cell = "", quoted = false, closed = false;
  const field = () => { row.push(cell); cell = ""; closed = false; };
  const record = () => {
    field(); rows.push(row); row = [];
    if (rows.length > 50001) throw new FinancialProjectionError("CSV exceeds 50,000 data rows.");
  };
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') { cell += '"'; i++; }
        else { quoted = false; closed = true; }
      } else cell += ch;
    } else if (ch === delimiter) field();
    else if (ch === "\n" || ch === "\r") {
      record(); if (ch === "\r" && text[i + 1] === "\n") i++;
    } else if (ch === '"' && !cell && !closed) quoted = true;
    else {
      if (closed || ch === '"') throw new FinancialProjectionError("CSV has malformed quoting. Nothing was uploaded.");
      cell += ch;
    }
  }
  if (quoted) throw new FinancialProjectionError("CSV has an unclosed quoted field. Nothing was uploaded.");
  if (cell || row.length || closed) record();
  return rows;
}

const fieldLabel = (key: string) => key === "type"
  ? "transaction type"
  : key.replaceAll("_", " ");

function invalid(message: string): never {
  // Do not include source cell/header contents in errors.  In particular,
  // patient names must never be reflected in a rejected upload message.
  throw new FinancialProjectionError(`${message} Nothing was uploaded.`);
}

function datePattern(format: string): RegExp | null {
  if (format === "%Y-%m-%d") return /^\d{4}-\d{2}-\d{2}$/;
  if (format === "%m/%d/%Y" || format === "%d/%m/%Y") return /^\d{2}\/\d{2}\/\d{4}$/;
  return null;
}

function validCalendarDate(value: string, format: string): boolean {
  const parts = format === "%Y-%m-%d" ? value.split("-") : value.split("/");
  if (parts.length !== 3) return false;
  const [year, month, day] = format === "%Y-%m-%d"
    ? parts.map(Number)
    : format === "%m/%d/%Y"
      ? [Number(parts[2]), Number(parts[0]), Number(parts[1])]
      : [Number(parts[2]), Number(parts[1]), Number(parts[0])];
  const date = new Date(Date.UTC(year, month - 1, day));
  return Number.isFinite(date.getTime()) && date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

function optionsFor(options: FinancialCSVOptions = {}) {
  return {
    sourceColumns: options.sourceColumns || {},
    defaults: options.defaults || {},
  };
}

/**
 * Return the source headers without exposing or returning row values.  The
 * parser still walks the complete local file so malformed quoting is caught
 * before a user can submit a mapping.
 */
export function csvHeaders(text: string, delimiter = ","): string[] {
  if (delimiter.length !== 1) invalid("The selected CSV delimiter is not supported.");
  if (text.includes("\0")) invalid("CSV contains unsupported characters.");
  const rows = parseCSV(text.replace(/^\uFEFF/, ""), delimiter);
  const header = rows.shift() || [];
  if (!header.length || new Set(header).size !== header.length || header.some((value) => !value.trim()))
    throw Error("The CSV needs unique, non-empty headers before financial columns can be mapped. Nothing was uploaded.");
  return header;
}

/**
 * Project an export to the exact server profile.  Source columns are resolved
 * before the output is built, so unselected columns (including identifiers)
 * never enter the returned CSV.  `financialCSV(text, profile)` retains the
 * original exact-header contract; options are used by the reviewable mapping
 * flow when a source export uses different labels or omits a whole-document
 * type/category column.
 */
export function financialCSV(
  text: string,
  profile: ColumnProfile,
  projectionOptions: FinancialCSVOptions = {},
) {
  if (!profile.delimiter || profile.delimiter.length !== 1)
    invalid("The selected profile has an unsupported CSV delimiter.");
  if (text.includes("\0")) invalid("CSV contains unsupported characters.");
  const rows = parseCSV(text.replace(/^\uFEFF/, ""), profile.delimiter);
  const header = rows.shift() || [];
  const columns: CSVColumn[] = Object.entries(profile.columns).map(([key, label]) => ({key, label}));
  const {sourceColumns, defaults} = optionsFor(projectionOptions);
  const profileKeys = new Set(columns.map(({key}) => key));
  if ([...Object.keys(sourceColumns), ...Object.keys(defaults)].some((key) => !profileKeys.has(key)))
    invalid("The mapping includes an unsupported financial field.");
  if (Object.values(defaults).some((value) => value !== undefined && typeof value !== "string"))
    invalid("Whole-file financial values must be text selected from the approved profile values.");
  if (!columns.length || new Set(columns.map(({label}) => label)).size !== columns.length)
    invalid("The selected profile has ambiguous financial column labels.");
  const hasProjectionOptions = Object.keys(sourceColumns).length > 0 || Object.keys(defaults).length > 0;
  if (!columns.length || !rows.length || new Set(header).size !== header.length ||
      columns.some(({label}) => !label || !header.includes(label)) &&
      !hasProjectionOptions)
    invalid("The CSV needs unique headers, all approved financial columns, and data rows.");

  const headerSet = new Set(header);
  const sourceByKey: Record<string, string | null> = {};
  const indices: Record<string, number> = {};
  const usedSources = new Set<string>();
  const allowedDefaults = new Set(["type", "category", "provider", "medical_insurance", "billing_code"]);

  for (const {key, label} of columns) {
    const hasExplicitSource = Object.prototype.hasOwnProperty.call(sourceColumns, key);
    const candidate = hasExplicitSource ? sourceColumns[key] || null : label;
    const source = candidate && headerSet.has(candidate) ? candidate : null;
    const defaultValue = Object.prototype.hasOwnProperty.call(defaults, key) ? defaults[key] : undefined;
    sourceByKey[key] = source;
    if (source) {
      if (usedSources.has(source)) invalid(`The same source column cannot be mapped to more than one financial field (${fieldLabel(key)}).`);
      usedSources.add(source);
      indices[key] = header.indexOf(source);
      if (defaultValue !== undefined && defaultValue !== "")
        invalid(`Choose either a source column or a whole-file default for ${fieldLabel(key)}; a mixed source needs a mapped per-row value.`);
      continue;
    }

    const missingAllowedDefault = allowedDefaults.has(key) && defaultValue !== undefined && defaultValue !== "";
    if (missingAllowedDefault) {
      if ((key === "type" || key === "category") && hasExplicitSource && headerSet.has(label))
        invalid(`Map the source column for ${fieldLabel(key)} per row; a whole-file value is only valid when that column is absent.`);
      const approved = profile.allowed_values[key] || [];
      if (!approved.includes(defaultValue as string))
        invalid(`The whole-file ${fieldLabel(key)} must be one of the approved profile values.`);
      continue;
    }
    if (key === "provider" || key === "medical_insurance" || key === "billing_code") {
      // An omitted provider/dimension is represented as an explicit blank in
      // the projected CSV.  No source value is guessed or retained.
      if (defaultValue !== undefined && defaultValue !== "")
        invalid(`The whole-file ${fieldLabel(key)} must be one of the approved profile values.`);
      continue;
    }
    if (key === "type" || key === "category")
      invalid(`Map a source column for ${fieldLabel(key)} or choose an approved whole-file ${fieldLabel(key)}.`);
    invalid(`Map a source column for ${fieldLabel(key)}; this field is required for every financial row.`);
  }

  const dateRegex = datePattern(profile.date_format);
  if (!dateRegex) invalid("The selected profile has an unsupported date format.");
  const output = [columns.map(({label}) => label)];
  rows.forEach((row, index) => {
    if (row.length !== header.length) invalid(`Row ${index + 2} has an incorrect field count.`);
    const values = columns.map(({key}) => {
      const source = sourceByKey[key];
      if (source) return row[indices[key]];
      if (Object.prototype.hasOwnProperty.call(defaults, key) && defaults[key] !== undefined && defaults[key] !== "")
        return defaults[key] as string;
      return "";
    });
    columns.forEach(({key}, position) => {
      const value = values[position];
      let valid = value.length <= 256;
      if (valid && key === "date") valid = dateRegex.test(value) && validCalendarDate(value, profile.date_format);
      else if (valid && key === "amount") valid = /^-?\d{1,16}(?:\.\d{1,2})?$/.test(value) &&
        (profile.allow_negative_amounts !== false || !value.startsWith("-"));
      else if (valid && ["provider", "medical_insurance", "billing_code"].includes(key))
        valid = !value || Boolean(profile.allowed_values[key]?.includes(value));
      else if (valid) valid = Boolean(profile.allowed_values[key]?.includes(value));
      if (!valid)
        invalid(`Row ${index + 2}: ${fieldLabel(key)} does not match the approved financial mapping. Check the selected column mapping and approved values.`);
    });
    output.push(values);
  });
  const quote = (value: string) => '"' + value.replaceAll('"', '""') + '"';
  const projected = columns.some(({key, label}) => sourceByKey[key] !== label) ||
    usedSources.size !== columns.length || header.length !== columns.length;
  return { csv: output.map((row) => row.map(quote).join(profile.delimiter)).join("\r\n") + "\r\n",
    records: output.slice(1).map(values => Object.fromEntries(columns.map(({key},i) => [key,values[i]]))),
    excludedColumns: Math.max(0, header.length - usedSources.size), projected, rows: rows.length };
}
