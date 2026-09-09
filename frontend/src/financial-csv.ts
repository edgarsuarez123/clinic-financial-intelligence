// Local-only projection: no network, persistence, logging, or raw-cell errors.
export type ColumnProfile = {
  columns: Record<string, string>;
  delimiter: string;
  date_format: string;
  allowed_values: Record<string, string[]>;
};

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
    if (rows.length > 50001) throw Error("CSV exceeds 50,000 data rows.");
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
      if (closed || ch === '"') throw Error("CSV has malformed quoting. Nothing was uploaded.");
      cell += ch;
    }
  }
  if (quoted) throw Error("CSV has an unclosed quoted field. Nothing was uploaded.");
  if (cell || row.length || closed) record();
  return rows;
}

export function financialCSV(text: string, profile: ColumnProfile) {
  if (text.includes("\0")) throw Error("CSV contains unsupported characters.");
  const rows = parseCSV(text.replace(/^\uFEFF/, ""), profile.delimiter);
  const header = rows.shift() || [];
  const columns = Object.entries(profile.columns);
  if (!rows.length || new Set(header).size !== header.length ||
      columns.some(([, label]) => !header.includes(label)))
    throw Error("The CSV needs unique headers, all approved financial columns, and data rows.");
  const indices = columns.map(([, label]) => header.indexOf(label));
  const output = [columns.map(([, label]) => label)];
  const datePattern = profile.date_format === "%Y-%m-%d" ? /^\d{4}-\d{2}-\d{2}$/ : /^\d{2}\/\d{2}\/\d{4}$/;
  rows.forEach((row, index) => {
    if (row.length !== header.length) throw Error(`Row ${index + 2} has an incorrect field count. Nothing was uploaded.`);
    const values = indices.map((position) => row[position]);
    columns.forEach(([key], position) => {
      const value = values[position];
      const valid = value.length <= 256 && (key === "date" ? datePattern.test(value) :
        key === "amount" ? /^-?\d{1,16}(?:\.\d{1,2})?$/.test(value) :
        ((!value && ["provider", "medical_insurance", "billing_code"].includes(key)) ||
          profile.allowed_values[key]?.includes(value)));
      if (!valid) throw Error(`Row ${index + 2}: ${key.replaceAll("_", " ")} does not match the approved financial mapping. Check the selected column mapping profile; existing demo installations may need a mapping upgrade. Nothing was uploaded.`);
    });
    output.push(values);
  });
  const quote = (value: string) => '"' + value.replaceAll('"', '""') + '"';
  return { csv: output.map((row) => row.map(quote).join(profile.delimiter)).join("\r\n") + "\r\n",
    records: output.slice(1).map(values => Object.fromEntries(columns.map(([key],i) => [key,values[i]]))),
    excludedColumns: header.length - columns.length, rows: rows.length };
}
