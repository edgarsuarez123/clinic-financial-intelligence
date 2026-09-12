import { financialCSV, type ColumnProfile } from "./financial-csv";

export type PDFColumn = {
  left: number;
  right: number;
  constant: string;
  useConstant: boolean;
};

export type PDFLayout = {
  firstPage: number;
  lastPage: number;
  top: number;
  bottom: number;
  columns: Record<string, PDFColumn>;
};

export type TextCell = {
  text: string;
  left: number;
  right: number;
  top: number;
};

function detailColumns(profile: ColumnProfile, layout: PDFLayout): [string, PDFColumn][] {
  const fields = Object.keys(profile.columns);
  if (!fields.length || !layout.columns)
    throw Error("Set the approved financial columns before extracting the PDF.");

  const columns = fields.map((key) => [key, layout.columns[key]] as [string, PDFColumn | undefined]);
  if (columns.some(([, column]) => !column))
    throw Error("Set a source for every approved financial column.");

  const complete = columns as [string, PDFColumn][];
  const ranges = complete.filter(([, column]) => !column.useConstant);
  if (ranges.some(([, column]) =>
    !Number.isFinite(column.left) || !Number.isFinite(column.right) ||
    column.left < 0 || column.right > 100 || column.left >= column.right,
  ))
    throw Error("Set non-overlapping financial column boundaries and a valid table area.");

  // Amount and billing code are row-level evidence. They cannot be replaced by
  // a statement-wide constant, even when a caller bypasses the rendered form.
  if (complete.some(([key, column]) =>
    (key === "amount" || key === "billing_code") && column.useConstant,
  ))
    throw Error("Paid amounts and billing codes must come from PDF detail columns.");

  if (!ranges.length || ranges.some(([, column], index) =>
    ranges.slice(index + 1).some(([, other]) => column.left < other.right && other.left < column.right),
  ))
    throw Error("Set non-overlapping financial column boundaries and a valid table area.");
  return ranges;
}

function validateLayout(profile: ColumnProfile, layout: PDFLayout): [string, PDFColumn][] {
  if (!Number.isFinite(layout.top) || !Number.isFinite(layout.bottom) ||
      layout.top < 0 || layout.top >= layout.bottom || layout.bottom > 100)
    throw Error("Set non-overlapping financial column boundaries and a valid table area.");
  return detailColumns(profile, layout);
}

/**
 * Project only explicitly selected PDF columns. Unmapped text, including names
 * and identifiers, never enters the returned rows.
 */
export function projectPage(items: TextCell[], layout: PDFLayout, profile: ColumnProfile): string[][] {
  validateLayout(profile, layout);
  const fields = Object.keys(profile.columns);
  const selected = items.filter((item) =>
    typeof item.text === "string" && item.text.trim() &&
    Number.isFinite(item.left) && Number.isFinite(item.right) && Number.isFinite(item.top) &&
    item.top >= layout.top && item.top <= layout.bottom,
  );
  const lines: TextCell[][] = [];
  for (const item of [...selected].sort((a, b) => a.top - b.top || a.left - b.left)) {
    const line = lines.find((row) => Math.abs(row[0].top - item.top) < 0.35);
    if (line) line.push(item);
    else lines.push([item]);
  }
  return lines.map((line) => fields.map((key) => {
    const column = layout.columns[key];
    if (column.useConstant) return column.constant;
    const overlapping = line.filter((item) => item.left < column.right && item.right > column.left);
    if (overlapping.some((item) => item.left < column.left || item.right > column.right))
      throw Error("A text cell crosses a financial column boundary. Adjust the layout; nothing was uploaded.");
    let value = overlapping
      .sort((a, b) => a.left - b.left)
      .map((item) => item.text)
      .join(" ")
      .trim();
    if (key === "amount" && /^\$?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?$/.test(value))
      value = value.replace(/[$,]/g, "");
    return value;
  }));
}

async function readPDFBytes(file: File): Promise<Uint8Array> {
  const candidate = file as File & { arrayBuffer?: () => Promise<ArrayBuffer> };
  if (typeof candidate.arrayBuffer === "function")
    return new Uint8Array(await candidate.arrayBuffer());
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
    reader.onerror = () => reject(reader.error || Error("The PDF could not be read."));
    reader.readAsArrayBuffer(file);
  });
}

export async function financialPDF(file: File, profile: ColumnProfile, layout: PDFLayout) {
  const pdfjs = await import("pdfjs-dist");
  pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    "pdfjs-dist/build/pdf.worker.min.mjs",
    import.meta.url,
  ).toString();
  const data = await readPDFBytes(file);
  if (data.byteLength > 10 * 1024 * 1024)
    throw Error("The PDF exceeds the 10 MiB limit.");
  const task = pdfjs.getDocument({
    data,
    isEvalSupported: false,
    verbosity: 0,
    useSystemFonts: true,
  });
  try {
    const pdf = await task.promise;
    if (
      pdf.numPages > 50 ||
      !Number.isInteger(layout.firstPage) ||
      !Number.isInteger(layout.lastPage) ||
      layout.firstPage < 1 ||
      layout.lastPage > pdf.numPages ||
      layout.firstPage > layout.lastPage
    )
      throw Error("Choose a valid page range within a PDF of at most 50 pages.");
    validateLayout(profile, layout);

    const rows: string[][] = [Object.values(profile.columns)];
    for (let pageNumber = layout.firstPage; pageNumber <= layout.lastPage; pageNumber += 1) {
      const page = await pdf.getPage(pageNumber);
      const viewport = page.getViewport({ scale: 1 });
      if (viewport.rotation !== 0) throw Error("Rotate the statement upright before importing.");
      const content = await page.getTextContent();
      const items = content.items.filter(
        (item): item is import("pdfjs-dist/types/src/display/api").TextItem => "str" in item,
      );
      if (!items.length)
        throw Error("Scanned PDFs are unsupported. Use a statement with selectable text.");
      rows.push(
        ...projectPage(
          items.map((item) => {
            const [left] = viewport.convertToViewportPoint(item.transform[4], item.transform[5]);
            const [right] = viewport.convertToViewportPoint(
              item.transform[4] + item.width,
              item.transform[5],
            );
            const [, top] = viewport.convertToViewportPoint(item.transform[4], item.transform[5]);
            return {
              text: item.str,
              left: Math.min(left, right) / viewport.width * 100,
              right: Math.max(left, right) / viewport.width * 100,
              top: top / viewport.height * 100,
            };
          }),
          layout,
          profile,
        ),
      );
      if (rows.length > 50001) throw Error("Statement exceeds 50,000 rows.");
    }
    const quote = (value: string) => `"${value.replaceAll("\"", "\"\"")}"`;
    return financialCSV(
      rows.map((row) => row.map(quote).join(profile.delimiter)).join("\r\n"),
      profile,
    );
  } finally {
    await task.destroy();
  }
}
