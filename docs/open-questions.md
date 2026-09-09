# Stakeholder decisions — no answers assumed

All eight Section 12 questions remain open:

1. Billing/practice-management system and actual export formats.
2. Historical backfill and range.
3. Whether benefits, malpractice and overhead are separate or bundled.
4. Whether revenue is attributed per provider.
5. Historical ramp-up evidence.
6. Authorized users and provider-compensation visibility.
7. A specific hiring case to validate.
8. Whether any upload can contain patient identifiers.

Before Phase 2 accepts clinic files, obtain answers to 1 and 8 and an approved
access policy from 6. Request a synthetic or explicitly sanitized representative
export, including its columns, units and date formats. Do not request a raw
patient billing export. Backfill in 2 determines the initial date range.

Additional specification decisions to resolve during the relevant phase:

- Soft deletion versus permanent deletion and backup/audit retention (ADR 009).
- Currency, negative adjustments/refunds and accounting date basis before imports.
- Treatment of partial reporting periods, missing periods versus zero activity,
  and expense allocation before analytics.
- Structured PDF extraction is F1.2 but absent from the condensed Phase 2 list;
  the SRD governs, so it remains in Phase 2 after CSV/XLSX. No OCR.
- A hash deduplicates byte-identical files only. Overlapping exports with changed
  ordering or formatting require a separate transaction identity decision.

These are unresolved inputs, not generated defaults. No role, compensation,
revenue, category, hire or calibration data has been seeded.

## Phase 2 update

The generic parsers and synthetic demo are implemented. All eight stakeholder
questions above remain unresolved. Default configuration keeps real imports disabled;
no mapping, role assignment or source-system behavior has been assumed.

## Phase 3 update

No stakeholder answers were supplied. Provider cost completeness and compensation
access remain unconfigured for real use. The analytics API returns explicit missing
results where attribution/cost evidence is insufficient. Streamlit is now explicitly
temporary; the final custom frontend is required before launch.


## Phase 5 update

Real-clinic questions remain unresolved. Remote LLM use additionally needs the chosen provider/model, executed DPA and written disclosure references, current token-price configuration, approved question/provider/cost-report access, and live translation evaluation. Local dev/test uses only labeled synthetic data and fixed demo prompts. Production still requires the Phase 6 controls and final frontend.
