from datetime import date
import pytest
from app.seed_dates import date_rows

def test_iso_year_boundary():
    rows=list(date_rows(date(2020,12,31),date(2021,1,1)))
    assert rows[1] == (20210101,date(2021,1,1),53,date(2020,12,28),2020,1,1,2021,5)

def test_leap_day_and_single_day():
    assert len(list(date_rows(date(2024,2,28),date(2024,3,1)))) == 3
    assert len(list(date_rows(date(2024,2,29),date(2024,2,29)))) == 1

def test_reversed_dates_rejected():
    with pytest.raises(ValueError):
        list(date_rows(date(2026,2,1),date(2026,1,1)))
