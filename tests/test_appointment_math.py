from datetime import date, timedelta
from decimal import Decimal

from app.appointments.aggregation import (
    AppointmentFact,
    aggregate_report,
    matched_prior_range,
    period_end,
    period_start,
)


D = Decimal


def fact(
    day: date,
    count: int,
    *,
    category: str = "new_patient",
    clinic: str = "North",
    billed: str | None = None,
    collected: str | None = None,
) -> AppointmentFact:
    return AppointmentFact(
        activity_date=day,
        clinic_location=clinic,
        category=category,
        appointment_count=count,
        billed_amount=None if billed is None else D(billed),
        collected_amount=None if collected is None else D(collected),
    )


def daily_week(start: date, first_count: int) -> list[AppointmentFact]:
    """Return an explicitly observed Monday-Sunday week, including zero days."""

    return [fact(start + timedelta(days=offset), first_count if offset == 0 else 0) for offset in range(7)]


def test_explicit_counts_and_decimal_totals_use_appointments_for_averages():
    start = date(2026, 1, 5)  # Monday
    end = date(2026, 1, 11)  # Sunday
    rows = [
        fact(start, 2, billed="120.00", collected="80.00"),
        fact(
            start + timedelta(days=1),
            3,
            category="follow_up",
            clinic="South",
            billed="30.00",
            collected="15.00",
        ),
    ]

    result = aggregate_report(rows, start, end, "week")
    summary = result["summary"]

    # The source supplies appointment volume explicitly.  It is not the row
    # count, and it is not inferred from either money field.
    assert summary["appointment_count"] == 5
    assert summary["row_count"] == 2
    assert summary["billed_amount"] == D("150.00")
    assert summary["collected_amount"] == D("95.00")
    assert isinstance(summary["billed_amount"], Decimal)
    assert isinstance(summary["collected_amount"], Decimal)

    # 150 / 5 and 95 / 5; dividing by the two source rows would be wrong.
    assert summary["average_billed_amount"] == D("30.00")
    assert summary["average_collected_amount"] == D("19.00")

    categories = {item["category"]: item for item in result["categories"]}
    assert categories["new_patient"]["appointment_count"] == 2
    assert categories["follow_up"]["appointment_count"] == 3

    period = result["periods"][0]
    assert period["appointment_count"] == 5
    assert period["billed_amount"] == D("150.00")
    assert period["collected_amount"] == D("95.00")


def test_missing_amounts_remain_unknown_and_zero_appointments_have_no_average():
    day = date(2026, 1, 5)

    unknown = aggregate_report([fact(day, 4)], day, day, "week")["summary"]
    assert unknown["appointment_count"] == 4
    assert unknown["billed_amount"] is None
    assert unknown["collected_amount"] is None
    assert unknown["billed_coverage"] == {"known_rows": 0, "total_rows": 1, "complete": False}
    assert unknown["collected_coverage"] == {"known_rows": 0, "total_rows": 1, "complete": False}
    assert unknown["average_billed_amount"] is None
    assert unknown["average_collected_amount"] is None

    zero = aggregate_report(
        [fact(day, 0, billed="0.00", collected="0.00")],
        day,
        day,
        "week",
    )["summary"]
    assert zero["appointment_count"] == 0
    assert zero["billed_amount"] == D("0.00")
    assert zero["collected_amount"] == D("0.00")
    assert zero["average_billed_amount"] is None
    assert zero["average_collected_amount"] is None


def test_week_period_is_inclusive_monday_through_sunday():
    monday = date(2026, 1, 5)
    sunday = date(2026, 1, 11)

    assert period_start(sunday, "week") == monday
    assert period_end(monday, "week") == sunday
    assert (period_end(monday, "week") - period_start(monday, "week")).days == 6

    result = aggregate_report(
        [fact(monday, 2), fact(sunday, 3)],
        monday,
        sunday,
        "week",
    )
    assert len(result["periods"]) == 1
    period = result["periods"][0]
    assert period["period_start"] == monday
    assert period["period_end"] == sunday
    assert period["appointment_count"] == 5


def test_previous_full_month_from_february_uses_january_month_end():
    assert matched_prior_range(
        date(2026, 2, 1),
        date(2026, 2, 28),
        "month",
    ) == (date(2026, 1, 1), date(2026, 1, 31))

    # The leap-year case protects the same month arithmetic at February's
    # other valid month end.
    assert matched_prior_range(
        date(2024, 2, 1),
        date(2024, 2, 29),
        "month",
    ) == (date(2024, 1, 1), date(2024, 1, 31))


def test_quarter_boundaries_and_matched_prior_quarter_are_calendar_aligned():
    start = date(2026, 4, 1)
    end = date(2026, 6, 30)

    assert period_start(date(2026, 5, 17), "quarter") == start
    assert period_end(start, "quarter") == end
    assert matched_prior_range(start, end, "quarter") == (
        date(2026, 1, 1),
        date(2026, 3, 31),
    )

    result = aggregate_report(
        [fact(start, 2), fact(end, 3)],
        start,
        end,
        "quarter",
    )
    assert len(result["periods"]) == 1
    assert result["periods"][0]["period_start"] == start
    assert result["periods"][0]["period_end"] == end
    assert result["periods"][0]["appointment_count"] == 5
    assert result["comparison"]["period_start"] == date(2026, 1, 1)
    assert result["comparison"]["period_end"] == date(2026, 3, 31)


def test_no_rows_are_unknown_and_do_not_imply_zero_growth():
    current_start = date(2026, 1, 5)
    current_end = date(2026, 1, 11)
    prior_start = date(2025, 12, 29)
    prior_end = date(2026, 1, 4)

    result = aggregate_report(
        [],
        current_start,
        current_end,
        "week",
        prior_rows=daily_week(prior_start, 10),
        prior_range=(prior_start, prior_end),
        prior_complete=True,
    )

    assert result["summary"]["observed"] is False
    assert result["summary"]["appointment_count"] is None
    assert result["periods"][0]["observed"] is False
    assert result["periods"][0]["appointment_count"] is None

    comparison = result["comparison"]
    assert comparison["observed"] is True
    assert comparison["current_observed"] is False
    assert comparison["appointment_count"] == 10
    assert comparison["change"] is None
    assert comparison["change_pct"] is None
    assert comparison["complete"] is True
    assert comparison["current_complete"] is False
    assert comparison["status"] == "partial_or_unavailable"


def test_incomplete_comparison_coverage_suppresses_delta():
    current_start = date(2026, 1, 5)
    current_end = date(2026, 1, 11)
    prior_start = date(2025, 12, 29)
    prior_end = date(2026, 1, 4)

    result = aggregate_report(
        [fact(current_start, 8)],
        current_start,
        current_end,
        "week",
        prior_rows=[fact(prior_start, 5)],
        prior_range=(prior_start, prior_end),
        prior_complete=False,
    )

    comparison = result["comparison"]
    assert comparison["observed"] is True
    assert comparison["current_observed"] is True
    assert comparison["appointment_count"] == 5
    assert comparison["change"] is None
    assert comparison["change_pct"] is None
    assert comparison["complete"] is False
    assert comparison["current_complete"] is False
    assert comparison["status"] == "partial_or_unavailable"


def test_zero_prior_count_has_unknown_percentage_but_known_absolute_change():
    current_start = date(2026, 1, 5)
    current_end = date(2026, 1, 11)
    prior_start = date(2025, 12, 29)
    prior_end = date(2026, 1, 4)

    result = aggregate_report(
        daily_week(current_start, 5),
        current_start,
        current_end,
        "week",
        prior_rows=daily_week(prior_start, 0),
        prior_range=(prior_start, prior_end),
        prior_complete=True,
        current_complete=True,
    )

    comparison = result["comparison"]
    assert comparison["appointment_count"] == 0
    assert comparison["change"] == 5
    assert comparison["change_pct"] is None

