# Appointment activity aggregates

The Patients & activity view reports **appointment volume** from an approved
aggregate export. It does not report unique people. Financial transaction rows,
procedure units, and appointment counts are separate measures; this release
stores no patient names, birth dates, identifiers, or clinical notes.

## Approved input

In React, open **Patients & activity**, download the synthetic CSV template,
replace its example values, and select **Validate & import**. Set the clinic
names to your approved `clinic_locations` in `config/ingestion.json` first.
The CSV requires all six headers below; optional monetary cells may be blank.
Unknown extra columns are rejected locally. Import status updates automatically,
and completion refreshes the activity report while preserving narrowed dates.
The checked-in example is `examples/appointment-activity.csv`; its numbers are
invented, and its example clinic is `North`.

The optional replacement field takes the upload ID shown in the import summary.
The original rows stay visible until the replacement finishes successfully.
Changing or overlapping a file does not automatically deduplicate its records.

`appointment_category_labels` optionally customizes canonical display labels;
`appointment_category_mappings` maps approved source labels to canonical keys.
Both are top-level ingestion configuration fields. Money uses the currency
already configured for the clinic's ingestion profiles.

The Patients & activity screen accepts a synthetic or system generated CSV with
this exact header set:

```text
date,clinic_location,category,appointment_count,billed_amount,collected_amount
```

Unknown extra columns are rejected. The browser validates the file against the
approved clinic list, canonical categories, and explicit source mappings from
`GET /api/v1/appointments/config`; it then sends only normalized aggregate rows
as JSON to `POST /api/v1/appointments/imports`. Blank money cells become JSON
`null`. The downloadable template contains synthetic rows only.

The API body contains `rows`. Each row has:

| Field | Requirement |
| --- | --- |
| `date` | ISO calendar date (`YYYY-MM-DD`) |
| `clinic_location` | A clinic name from the configured approved list |
| `category` | A canonical category or a source value with an explicit configured mapping |
| `appointment_count` | Nonnegative integer; zero is a valid explicit observation |
| `billed_amount` | Optional decimal amount with at most two places |
| `collected_amount` | Optional decimal amount with at most two places |

The initial canonical categories are `new_patient`, `radiology`, `lab`,
`follow_up`, `preventive`, and `other`. Source labels are accepted only when
an administrator maps them to one of these keys. Unknown columns and unknown
categories are rejected. Missing money remains unknown (`null`); it is never
converted to zero.

The optional `source_hash` identifies the source export for audit context. The
server computes the normalized content hash from the approved rows and uses
that canonical hash for idempotency. Repeating the same normalized batch does
not add counts. A changed or overlapping export requires the explicit
`replace_upload_id` field; overlap alone never replaces an existing source.

The UI polls `GET /api/v1/appointments/imports/{upload_id}` while an import is
pending or processing. A failed import remains visible and can be retried with
`POST /api/v1/appointments/imports/{upload_id}/retry`. A completed import
refreshes appointment metadata and the report without resetting a deliberately
narrowed date range. To replace an existing completed source, pass its upload ID
as `replace_upload_id` in a new import; the UI never infers replacement from
overlapping dates.

## Synthetic example

```json
{
  "rows": [
    {
      "date": "2026-09-07",
      "clinic_location": "North",
      "category": "new_patient",
      "appointment_count": 8,
      "billed_amount": "960.00",
      "collected_amount": "720.00"
    },
    {
      "date": "2026-09-07",
      "clinic_location": "North",
      "category": "follow_up",
      "appointment_count": 12,
      "billed_amount": "840.00",
      "collected_amount": null
    },
    {
      "date": "2026-09-08",
      "clinic_location": "North",
      "category": "new_patient",
      "appointment_count": 0,
      "billed_amount": "0.00",
      "collected_amount": "0.00"
    }
  ]
}
```

For a complete daily comparison, include an explicit row, including a zero
count row, for every date in both selected and matched prior periods. A period
with no row is unknown. Billed and collected totals are displayed separately
from financial revenue and do not augment the financial ledger.

## Access and processing

Reading uses the configured analytics/read permission. Import, retry, source
replacement, and soft deletion use the configured ingestion/write permission.
Imports are queued and processed by the durable worker. Category and clinic
configuration is snapshotted with the job so a later configuration edit cannot
reinterpret an already accepted source. Source rows and audit records are
append-only; deletion is a recorded soft deletion that removes the source from
the reporting view.
