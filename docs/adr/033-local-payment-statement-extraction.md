# 033 — Local extraction of insurer payment statement tables

Source statements may contain names even though the application persists only financial data. The React client therefore reads PDFs locally with a bundled PDF.js worker and uploads a validated CSV projection. It never sends original PDF bytes through this workflow. The server's existing exact schema, approved dimensions, decimal validation, authorization and asynchronous idempotent persistence remain the final boundary.

Users explicitly specify page range, table area and column bounds; statement-wide financial values can be entered from approved mappings. Amount and billing code must come from detail columns. Cross-boundary cells, incomplete rows, unknown codes and invalid amounts stop submission. Headings, footers and totals must lie outside the selected detail area. The extracted financial CSV requires review and confirmation. This does not certify deidentification or resolve the standing source-PHI policy review.

No heuristic guesses, OCR, external LLM extraction or arbitrary insurer recognition are introduced. A representative insurer statement is needed to validate its layout and reconcile totals before use. Unsupported layouts require financial-only CSV exports. Original bytes, extracted patient text and filenames are not sent or persisted by the PDF workflow. Layout edits invalidate previously confirmed output.

PDF.js is dynamically imported and its worker is bundled locally. This adds a larger on-demand import payload while preserving the initial application bundle. Chart coordinate conversion remains separate from exact decimal arithmetic.
