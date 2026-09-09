# Explicit export contracts

Status: Accepted until source samples are provided

Decision: All five mapped headers are required, with no additional columns. Empty provider values mean unattributed; other required fields reject blanks. Dates use one configured exact format; amounts are plain decimals of at most two fractional digits. Read XLSX amount values from XML text. Reject formulas, hidden rows/sheets, multiple worksheets, merged cells and active external content. PDF extraction uses an explicit lines/text strategy; every page must yield a matching table.

Consequences: Rejecting an unsupported layout is preferable to silently dropping a worksheet or inventing an amount/date. These restrictions may require format-specific adapters after Section 12 question 1 is answered. No sample from a real billing system has been validated.
