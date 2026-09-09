import { financialCSV, type ColumnProfile } from './financial-csv';
export type PDFColumn = { left: number; right: number; constant: string; useConstant: boolean };
export type PDFLayout = { firstPage: number; lastPage: number; top: number; bottom: number; columns: Record<string, PDFColumn> };
export type TextCell = { text: string; left: number; right: number; top: number };
// Coordinates are percentages of each page. Only explicitly selected columns leave this function.
export function projectPage(items: TextCell[], layout: PDFLayout, profile: ColumnProfile): string[][] {
  const fields = Object.keys(profile.columns);
  const ranges = fields.filter(k => !layout.columns[k]?.useConstant).map(k => layout.columns[k]);
  if (!ranges.length || ranges.some(c => !c || c.left < 0 || c.right > 100 || c.left >= c.right) ||
      ranges.some((a,i) => ranges.slice(i+1).some(b => a.left < b.right && b.left < a.right)) ||
      !(layout.top >= 0 && layout.top < layout.bottom && layout.bottom <= 100))
    throw Error('Set non-overlapping financial column boundaries and a valid table area.');
  const selected = items.filter(t => t.top >= layout.top && t.top <= layout.bottom && t.text.trim());
  const lines: TextCell[][] = [];
  for (const item of [...selected].sort((a,b) => a.top-b.top || a.left-b.left)) {
    const line = lines.find(r => Math.abs(r[0].top-item.top) < 0.35);
    if (line) line.push(item); else lines.push([item]);
  }
  return lines.map(line => fields.map(key => {
    const c = layout.columns[key];
    if (c.useConstant) return c.constant;
    const overlapping = line.filter(t => t.left < c.right && t.right > c.left);
    if (overlapping.some(t => t.left < c.left || t.right > c.right))
      throw Error('A text cell crosses a financial column boundary. Adjust the layout; nothing was uploaded.');
    let value = overlapping.sort((a,b) => a.left-b.left).map(t => t.text).join(' ').trim();
    if (key === 'amount' && /^\$?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?$/.test(value)) value = value.replace(/[$,]/g,'');
    return value;
  }));
}
export async function financialPDF(file: File, profile: ColumnProfile, layout: PDFLayout) {
  const pdfjs = await import('pdfjs-dist');
  pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString();
  const task = pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()), isEvalSupported: false, verbosity: 0, useSystemFonts: true });
  try {
    const pdf = await task.promise;
    if (pdf.numPages > 50 || !Number.isInteger(layout.firstPage) || !Number.isInteger(layout.lastPage) || layout.firstPage < 1 || layout.lastPage > pdf.numPages || layout.firstPage > layout.lastPage)
      throw Error('Choose a valid page range within a PDF of at most 50 pages.');
    const rows: string[][] = [Object.values(profile.columns)];
    for (let pageNumber=layout.firstPage; pageNumber<=layout.lastPage; pageNumber++) {
      const page = await pdf.getPage(pageNumber);
      const viewport = page.getViewport({scale:1});
      if (viewport.rotation !== 0) throw Error('Rotate the statement upright before importing.');
      const content = await page.getTextContent();
      const items = content.items.filter((t): t is import('pdfjs-dist/types/src/display/api').TextItem => 'str' in t);
      if (!items.length) throw Error('Scanned PDFs are unsupported. Use a statement with selectable text.');
      rows.push(...projectPage(items.map(t => {const [x,y]=viewport.convertToViewportPoint(t.transform[4],t.transform[5]);return {text:t.str, left:x/viewport.width*100, right:(x+t.width)/viewport.width*100, top:y/viewport.height*100};}), layout, profile));
      if (rows.length > 50001) throw Error('Statement exceeds 50,000 rows.');
    }
    const quote = (v:string) => '"'+v.replaceAll('"','""')+'"';
    return financialCSV(rows.map(row => row.map(quote).join(profile.delimiter)).join('\r\n'), profile);
  } finally { await task.destroy(); }
}
