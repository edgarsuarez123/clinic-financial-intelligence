from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator

def decimal_string(v):
    if not isinstance(v,str) or len(v)>40: raise ValueError('Enter a decimal string, not a JSON floating-point number')
    return v
Amount=Annotated[Decimal,BeforeValidator(decimal_string),Field(ge=0,le=1000000000000,allow_inf_nan=False)]
Text=Annotated[str,Field(min_length=1,max_length=500)]
class Model(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Revenue(Model):
    kind: Literal['manual','historical']
    monthly_revenue: Amount | None = None
    basis: Text
    provider_keys: list[UUID] = Field(default_factory=list,max_length=50)
    start: date | None = None
    end: date | None = None
class Staff(Model):
    role_type: Text
    headcount: int = Field(strict=True,ge=1,le=500)
    start_month: int = Field(strict=True,ge=1,le=120)
    end_month: int = Field(strict=True,ge=1,le=120)
    revenue_mode: Literal['included_in_clinic_baseline','incremental','none']
    annual_salary: Amount
    benefits_pct: Amount
    payroll_tax_pct: Amount
    annual_malpractice: Amount
    annual_other_fixed_cost: Amount
    onboarding_cost: Amount
    variable_cost_pct: Amount
    cost_basis: Text
    revenue: Revenue
    monthly_salary: dict[int,Amount] = Field(default_factory=dict,max_length=120)
class Cost(Model):
    label: Text
    monthly_amount: Amount
    one_time_amount: Amount
    start_month: int = Field(strict=True,ge=1,le=120)
    end_month: int = Field(strict=True,ge=1,le=120)
    monthly_amounts: dict[int,Amount] = Field(default_factory=dict,max_length=120)
class Step(Model):
    month: int = Field(strict=True,ge=1,le=120)
    productivity: Amount
class ScenarioInput(Model):
    name: Literal['pessimistic','expected','optimistic']
    revenue_multiplier: Amount
    fixed_cost_multiplier: Amount
    ramp: list[Step] = Field(min_length=1,max_length=120)
    ramp_basis: Text
    volume_multiplier: Amount = Decimal('1')
    payment_multiplier: Amount = Decimal('1')

class RevenueDriver(Model):
    insurance: Text
    billing_code: Text
    monthly_units: Amount
    collected_per_unit: Amount
    units_by_month: dict[int,Amount] = Field(default_factory=dict,max_length=120)
    payment_by_month: dict[int,Amount] = Field(default_factory=dict,max_length=120)

class BaselineSnapshot(Model):
    start: date
    end: date
    clinic_location: str | None = Field(default=None,max_length=200)
    revenue: Amount
    costs: list[Cost] = Field(max_length=50)
class PlanInput(Model):
    start_date: date
    months: int = Field(strict=True,ge=1,le=120)
    currency: str = Field(pattern='^[A-Z]{3}$')
    existing_monthly_revenue: Amount
    existing_revenue_by_month: dict[int,Amount] = Field(default_factory=dict,max_length=120)
    existing_revenue_basis: Text
    staff: list[Staff] = Field(max_length=30)
    clinic_costs: list[Cost] = Field(max_length=50)
    scenarios: list[ScenarioInput] = Field(min_length=3,max_length=3)
    revenue_mode: Literal['amount','drivers'] = 'amount'
    revenue_drivers: list[RevenueDriver] = Field(default_factory=list,max_length=50)
    baseline: BaselineSnapshot | None = None
    variable_cost_pct: Amount = Decimal('0')

class BudgetInput(Model):
    name: str = Field(min_length=1,max_length=100)
    plan: PlanInput
class CreateBudget(BudgetInput):
    budget_id: UUID
class UpdateBudget(BudgetInput):
    expected_revision: int = Field(strict=True,ge=1)

class BudgetRevision(Model):
    expected_revision: int = Field(strict=True,ge=1)
