"""OpenAPI response contracts. Numeric financial results are decimal strings."""
from datetime import date
from pydantic import BaseModel, Field

class Category(BaseModel):
    category_key: str
    category_type: str
    amount: str
    pct_revenue: str | None

class Summary(BaseModel):
    observed: bool
    row_count: int
    revenue: str | None
    expense: str | None
    net: str | None
    margin_pct: str | None
    fixed_cost: str | None
    variable_cost: str | None
    categories: list[Category]

class MovingAverage(BaseModel):
    value: str | None
    observed_periods: int
    calendar_periods: int
    target_periods: int
    complete_window: bool

class Period(Summary):
    period_start: date
    period_end: date
    coverage_start: date
    coverage_end: date
    partial: bool
    revenue_growth_pct: str | None
    expense_growth_pct: str | None
    growth_comparable: bool
    revenue_ma_4: MovingAverage | None = None
    revenue_ma_12: MovingAverage | None = None
    expense_ma_4: MovingAverage | None = None
    expense_ma_12: MovingAverage | None = None

class Variation(BaseModel):
    value: str | None
    samples: int
    reason: str | None

class Volatility(BaseModel):
    frequency: str
    basis: str
    revenue: Variation
    expense: Variation
    missing_weeks: int
    partial_weeks: int

class DashboardResponse(BaseModel):
    start: date
    end: date
    summary: Summary
    weekly: list[Period]
    monthly: list[Period]
    volatility: Volatility
    data_notes: list[str]
    currency: str | None
    category_labels: dict[str,str]

class MetadataResponse(BaseModel):
    first_date: date | None
    last_date: date | None
    row_count: int

class ProviderContribution(BaseModel):
    provider_key: str
    label: str
    revenue: str
    attributed_expense: str
    fully_loaded_cost: str | None
    contribution: str | None
    contribution_margin_pct: str | None
    cost_complete: bool
    cost_basis: str | None
    status: str

class Unattributed(BaseModel):
    observed: bool
    row_count: int
    revenue: str | None
    expense: str | None
    net: str | None
    margin_pct: str | None
    fixed_cost: str | None
    variable_cost: str | None

class ProvidersResponse(BaseModel):
    start: date
    end: date
    providers: list[ProviderContribution]
    unattributed: Unattributed
    notes: list[str]
    currency: str | None
