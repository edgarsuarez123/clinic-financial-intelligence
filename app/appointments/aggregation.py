"""Pure appointment-volume aggregation.

The functions in this module only operate on already-approved aggregate rows.
They never derive a visit from a billing row and never expose a person-level
measure.  Decimal arithmetic remains Decimal until the HTTP JSON boundary.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Context, Decimal, InvalidOperation, localcontext
from typing import Iterable, Mapping, Sequence

from .config import DEFAULT_CATEGORY_LABELS


FREQUENCIES = {"week", "month", "quarter"}


@dataclass(frozen=True)
class AppointmentFact:
    activity_date: date
    clinic_location: str
    category: str
    appointment_count: int
    billed_amount: Decimal | None = None
    collected_amount: Decimal | None = None

    def __post_init__(self) -> None:
        if type(self.activity_date) is not date:
            raise TypeError("activity_date must be a date")
        if (
            not isinstance(self.clinic_location, str)
            or
            not self.clinic_location
            or self.clinic_location != self.clinic_location.strip()
            or self.clinic_location == "Unassigned"
        ):
            raise ValueError("clinic_location is required")
        if not isinstance(self.category, str) or not self.category:
            raise ValueError("category is required")
        if isinstance(self.appointment_count, bool) or not isinstance(self.appointment_count, int):
            raise TypeError("appointment_count must be an integer")
        if self.appointment_count < 0:
            raise ValueError("appointment_count cannot be negative")
        for value, name in ((self.billed_amount, "billed_amount"), (self.collected_amount, "collected_amount")):
            if value is None:
                continue
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be Decimal or None")
            if (
                not value.is_finite()
                or abs(value) >= Decimal("10000000000000000")
                or value.as_tuple().exponent < -2
            ):
                raise ValueError(
                    f"{name} must be a finite amount within the supported range with at most two decimals"
                )


def _as_fact(row: AppointmentFact | Mapping[str, object]) -> AppointmentFact:
    if isinstance(row, AppointmentFact):
        return row
    value = dict(row)
    day = value.get("activity_date", value.get("date"))
    if isinstance(day, str):
        day = date.fromisoformat(day)
    def amount(key: str) -> Decimal | None:
        item = value.get(key)
        if item is None:
            return None
        return item if isinstance(item, Decimal) else Decimal(str(item))
    count = value.get("appointment_count", 0)
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError("appointment_count must be an integer")
    return AppointmentFact(
        activity_date=day,  # type: ignore[arg-type]
        clinic_location=value.get("clinic_location", ""),  # type: ignore[arg-type]
        category=value.get("category", value.get("category_key", "")),  # type: ignore[arg-type]
        appointment_count=count,
        billed_amount=amount("billed_amount"),
        collected_amount=amount("collected_amount"),
    )


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def add_months(day: date, months: int) -> date:
    """Shift a date by whole calendar months, clamping month-end days."""

    index = day.year * 12 + day.month - 1 + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    return date(year, month, min(day.day, _last_day(year, month)))


def _is_month_start(day: date) -> bool:
    return day.day == 1


def _is_month_end(day: date) -> bool:
    return day.day == _last_day(day.year, day.month)


def _quarter_start(day: date) -> date:
    return date(day.year, ((day.month - 1) // 3) * 3 + 1, 1)


def _quarter_end(day: date) -> date:
    start = _quarter_start(day)
    end_month = start.month + 2
    return date(start.year, end_month, _last_day(start.year, end_month))


def period_start(day: date, frequency: str) -> date:
    if frequency == "week":
        return day - timedelta(days=day.weekday())
    if frequency == "month":
        return date(day.year, day.month, 1)
    if frequency == "quarter":
        return _quarter_start(day)
    raise ValueError("frequency must be week, month, or quarter")


def period_end(day: date, frequency: str) -> date:
    if frequency == "week":
        return period_start(day, frequency) + timedelta(days=6)
    if frequency == "month":
        return date(day.year, day.month, _last_day(day.year, day.month))
    if frequency == "quarter":
        return _quarter_end(day)
    raise ValueError("frequency must be week, month, or quarter")


def iter_period_starts(start: date, end: date, frequency: str) -> Iterable[date]:
    if frequency not in FREQUENCIES:
        raise ValueError("frequency must be week, month, or quarter")
    cursor = period_start(start, frequency)
    last = period_start(end, frequency)
    while cursor <= last:
        yield cursor
        cursor = cursor + timedelta(days=7) if frequency == "week" else add_months(cursor, 1 if frequency == "month" else 3)


def matched_prior_range(start: date, end: date, frequency: str) -> tuple[date, date]:
    """Return the immediately preceding range with the same selected shape."""

    if start > end:
        raise ValueError("start must not be after end")
    if frequency not in FREQUENCIES:
        raise ValueError("frequency must be week, month, or quarter")
    if frequency == "week" and start.weekday() == 0 and end.weekday() == 6:
        weeks = (end - start).days // 7 + 1
        prior_start = start - timedelta(days=weeks * 7)
        return prior_start, prior_start + timedelta(days=weeks * 7 - 1)
    if frequency == "month" and _is_month_start(start) and _is_month_end(end):
        months = (end.year - start.year) * 12 + end.month - start.month + 1
        prior_start = add_months(start, -months)
        prior_end = start - timedelta(days=1)
        return prior_start, prior_end
    if frequency == "quarter" and start == _quarter_start(start) and end == _quarter_end(end):
        quarters = ((end.year - start.year) * 12 + end.month - start.month) // 3 + 1
        prior_start = add_months(start, -quarters * 3)
        prior_end = start - timedelta(days=1)
        return prior_start, prior_end
    days = (end - start).days + 1
    prior_end = start - timedelta(days=1)
    return prior_end - timedelta(days=days - 1), prior_end


def _amount_total(rows: Sequence[AppointmentFact], field: str) -> tuple[Decimal | None, dict[str, object]]:
    known = [getattr(row, field) for row in rows if getattr(row, field) is not None]
    total = len(rows)
    if not known:
        value: Decimal | None = None
    else:
        value = sum(known, Decimal("0"))
    coverage = {"known_rows": len(known), "total_rows": total, "complete": bool(total and len(known) == total)}
    return value, coverage


def _date_coverage_complete(rows: Sequence[AppointmentFact], start: date, end: date) -> bool:
    """Whether an aggregate contains an explicit row for every selected day."""

    if start > end or not rows:
        return False
    observed = {row.activity_date for row in rows if start <= row.activity_date <= end}
    return len(observed) == (end - start).days + 1


def _period_row(rows: Sequence[AppointmentFact], start: date, end: date, frequency: str) -> dict[str, object]:
    period_rows = [row for row in rows if period_start(row.activity_date, frequency) == start]
    # No aggregate row means the period is unknown.  Preserve an explicit
    # zero-count row as a known zero instead of conflating the two states.
    count = sum(row.appointment_count for row in period_rows) if period_rows else None
    billed, billed_coverage = _amount_total(period_rows, "billed_amount")
    collected, collected_coverage = _amount_total(period_rows, "collected_amount")
    actual_start = max(start, min((row.activity_date for row in period_rows), default=start))
    actual_end = min(end, max((row.activity_date for row in period_rows), default=end))
    observed = bool(period_rows)
    coverage_complete = _date_coverage_complete(period_rows, start, end)
    return {
        "period_start": start,
        "period_end": end,
        "coverage_start": actual_start,
        "coverage_end": actual_end,
        # A period with no aggregate row is unknown.  A zero-count row is an
        # explicit observation and therefore remains a known zero.
        "observed": observed,
        "partial": bool(observed and (actual_start != start or actual_end != end)) or bool(period_rows and not coverage_complete),
        "coverage_complete": coverage_complete,
        "appointment_count": count,
        "billed_amount": billed,
        "collected_amount": collected,
        "billed_coverage": billed_coverage,
        "collected_coverage": collected_coverage,
        "row_count": len(period_rows),
    }


def _summary(rows: Sequence[AppointmentFact], labels: Mapping[str, str]) -> dict[str, object]:
    billed, billed_coverage = _amount_total(rows, "billed_amount")
    collected, collected_coverage = _amount_total(rows, "collected_amount")
    # An empty result is unavailable data, not an observed zero.  An explicit
    # row carrying appointment_count=0 remains a known zero.
    appointment_count = sum(row.appointment_count for row in rows) if rows else None
    return {
        "observed": bool(rows),
        "appointment_count": appointment_count,
        "row_count": len(rows),
        "billed_amount": billed,
        "collected_amount": collected,
        "billed_coverage": billed_coverage,
        "collected_coverage": collected_coverage,
        # Averages are intentionally unknown unless every aggregate row has
        # an amount; a partial export must never look complete.
        "average_billed_amount": (
            billed / Decimal(appointment_count)
            if billed is not None and appointment_count and billed_coverage["complete"]
            else None
        ),
        "average_collected_amount": (
            collected / Decimal(appointment_count)
            if collected is not None and appointment_count and collected_coverage["complete"]
            else None
        ),
        "category_labels": dict(labels),
    }


def _comparison(
    current: Sequence[AppointmentFact],
    prior: Sequence[AppointmentFact],
    prior_start: date,
    prior_end: date,
    prior_complete: bool,
    current_complete: bool,
) -> dict[str, object]:
    current_count = sum(row.appointment_count for row in current)
    prior_count = sum(row.appointment_count for row in prior)
    change = current_count - prior_count
    change_pct = (Decimal(change) * Decimal("100") / Decimal(prior_count)) if prior_count else None
    return {
        "period_start": prior_start,
        "period_end": prior_end,
        "observed": bool(prior),
        "appointment_count": prior_count if prior else None,
        # A partial prior export can show its observed count, but it cannot
        # support a matched-period delta without claiming completeness.
        "current_observed": bool(current),
        "change": change if prior_complete and current_complete else None,
        "change_pct": change_pct if prior_complete and current_complete else None,
        "complete": prior_complete,
        "current_complete": current_complete,
        "status": "complete" if prior_complete and current_complete else "partial_or_unavailable",
    }


def _aggregate_report(
    rows: Iterable[AppointmentFact | Mapping[str, object]],
    start: date,
    end: date,
    frequency: str = "week",
    *,
    labels: Mapping[str, str] | None = None,
    prior_rows: Iterable[AppointmentFact | Mapping[str, object]] | None = None,
    prior_range: tuple[date, date] | None = None,
    prior_complete: bool = False,
    current_complete: bool | None = None,
) -> dict[str, object]:
    """Aggregate appointment facts for a selected range and comparison range."""

    if start > end:
        raise ValueError("start must not be after end")
    if frequency not in FREQUENCIES:
        raise ValueError("frequency must be week, month, or quarter")
    labels = dict(labels or DEFAULT_CATEGORY_LABELS)
    if prior_range is None:
        prior_range = matched_prior_range(start, end, frequency)
    normalized_current = [_as_fact(row) for row in rows]
    current = [row for row in normalized_current if start <= row.activity_date <= end]
    prior = [
        row
        for row in (_as_fact(item) for item in (prior_rows or []))
        if prior_range is None or prior_range[0] <= row.activity_date <= prior_range[1]
    ]
    if current_complete is None:
        current_complete = _date_coverage_complete(current, start, end)
    else:
        # A caller-provided completeness flag cannot turn an empty result into
        # an observed range.
        current_complete = bool(current_complete and current)
    prior_complete = bool(prior_complete and prior)
    periods = [
        _period_row(current, p, period_end(p, frequency), frequency)
        for p in iter_period_starts(start, end, frequency)
    ]

    category_rows: list[dict[str, object]] = []
    for category in labels:
        selected = [row for row in current if row.category == category]
        billed, billed_coverage = _amount_total(selected, "billed_amount")
        collected, collected_coverage = _amount_total(selected, "collected_amount")
        category_rows.append({
            "category": category,
            "label": labels[category],
            # A missing category row is unknown; an explicit zero-count row is
            # retained as a known zero observation.
            "appointment_count": sum(row.appointment_count for row in selected) if selected else None,
            "billed_amount": billed,
            "collected_amount": collected,
            "billed_coverage": billed_coverage,
            "collected_coverage": collected_coverage,
        })
    # A configured source may contain a canonical category added after the
    # report labels were built.  Preserve it without guessing a display name.
    for category in sorted({row.category for row in current} - set(labels)):
        selected = [row for row in current if row.category == category]
        billed, billed_coverage = _amount_total(selected, "billed_amount")
        collected, collected_coverage = _amount_total(selected, "collected_amount")
        category_rows.append({
            "category": category,
            "label": category,
            "appointment_count": sum(row.appointment_count for row in selected) if selected else None,
            "billed_amount": billed,
            "collected_amount": collected,
            "billed_coverage": billed_coverage,
            "collected_coverage": collected_coverage,
        })
    locations: dict[str, int] = {}
    for row in current:
        locations[row.clinic_location] = locations.get(row.clinic_location, 0) + row.appointment_count
    return {
        "measure": "appointment_volume",
        "measure_label": "Appointments (aggregate volume)",
        "not_unique_patients": True,
        "start": start,
        "end": end,
        "frequency": frequency,
        "summary": _summary(current, labels),
        "periods": periods,
        "categories": category_rows,
        "locations": [{"clinic_location": name, "appointment_count": count} for name, count in sorted(locations.items())],
        "coverage_complete": current_complete,
        "comparison": _comparison(
            current,
            prior,
            prior_range[0],
            prior_range[1],
            prior_complete,
            current_complete,
        ),
    }


def aggregate_report(
    rows: Iterable[AppointmentFact | Mapping[str, object]],
    start: date,
    end: date,
    frequency: str = "week",
    *,
    labels: Mapping[str, str] | None = None,
    prior_rows: Iterable[AppointmentFact | Mapping[str, object]] | None = None,
    prior_range: tuple[date, date] | None = None,
    prior_complete: bool = False,
    current_complete: bool | None = None,
) -> dict[str, object]:
    """Aggregate appointment facts under a high precision Decimal context."""

    with localcontext(Context(prec=50)):
        return _aggregate_report(
            rows,
            start,
            end,
            frequency,
            labels=labels,
            prior_rows=prior_rows,
            prior_range=prior_range,
            prior_complete=prior_complete,
            current_complete=current_complete,
        )


# Friendly aliases for callers that want the operation name rather than the
# HTTP response name.
aggregate_appointments = aggregate_report
aggregate = aggregate_report
