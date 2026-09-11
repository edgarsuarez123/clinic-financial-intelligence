# Realistic synthetic clinic

Import these two files into a disposable dev/test clinic:

| File | Mapping profile | Contents |
| --- | --- | --- |
| staff-costs.csv | staff-costs | 846 expense rows: 12 fictional employees, salary, benefits, assumed payroll taxes, malpractice, rent, utilities, software, insurance and supplies |
| medical-billing.csv | medical-billing | 29,834 daily financial aggregates for six fictional clinicians, six insurers and five billing codes |

Coverage: March 1, 2025 through August 31, 2026. No patient information.
All names of employees, amounts, payer mix and compensation are invented.
Benefits (30%) and payroll taxes (9.5%) are sample assumptions, not legal rates.
Support staff use internal provider identifiers solely for expense attribution;
they have no billed clinical activity. Cost completeness is not automatically certified.

Real insurer labels: Aetna, Humana, UnitedHealthcare, Cigna, Triple-S Salud, MCS.
Real code identifiers: 99202, 99203, 99212, 99213, 99214. No actual reimbursement
rates or official code descriptions are supplied.
Code identifier reference: https://www.cms.gov/httpswwwcmsgovresearch-statistics-data-and-systemsmonitoring-programsmedicare-ffs-compliance/0042-evaluation-and-management-services-office-or-other-outpatient-visit-billed-hospital-inpatients

Generate the checked-in 18-month fixtures with `python -m app.demo_data --full`.
Without `--full`, the command writes only the first 1,500 billing rows.
New demo setup includes both mapping profiles. For an existing demo, see the
realistic fixture upgrade section in `how-to-run.md`. Do not combine these files
with older overlapping sample ledgers when evaluating clinic totals. Changed
files with overlapping transactions are not deduplicated by content hashing.
