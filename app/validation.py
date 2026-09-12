"""Safe field guidance: never echo rejected values or arbitrary mapping keys."""
from .simulation.schemas import PlanInput, Staff, Cost, Revenue, ScenarioInput, Step, RevenueDriver, BaselineSnapshot

FIELDS = {"body", "plan", "name", "budget_id", "expected_revision"}
for model in (PlanInput, Staff, Cost, Revenue, ScenarioInput, Step, RevenueDriver, BaselineSnapshot):
    FIELDS.update(model.model_fields)


def simulation_issues(errors):
    issues = []
    for item in errors[:8]:
        parts = [str(p) if type(p) is int or p in FIELDS else "field" for p in item.get("loc", ())]
        if parts and parts[0] == "body": parts = parts[1:]
        kind = item.get("type", "")
        if kind == "missing": message = "This field is required."
        elif kind in {"string_too_short", "too_short"}: message = "Enter a value before saving."
        elif kind in {"int_type", "int_parsing"}: message = "Enter a whole number."
        elif kind in {"greater_than_equal", "greater_than", "less_than_equal", "less_than"}: message = "Enter a value within the allowed range."
        elif kind.startswith("date_"): message = "Enter a valid date."
        elif kind == "extra_forbidden": message = "This field is not supported."
        else: message = "Check this value and its required format."
        issues.append({"field": ".".join(parts) or "plan", "message": message})
    return issues
