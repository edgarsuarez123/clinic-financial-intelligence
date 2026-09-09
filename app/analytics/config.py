from datetime import date
from pathlib import Path
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .calculations import CostCoverage

class Coverage(BaseModel):
    model_config=ConfigDict(extra="forbid")
    start: date
    end: date
    basis: str = Field(min_length=1,max_length=500)
    @model_validator(mode="after")
    def validate_range(self):
        CostCoverage(self.start,self.end,self.basis)
        return self

class AnalyticsConfig(BaseModel):
    model_config=ConfigDict(extra="forbid")
    synthetic_data: bool = False
    authorized_user_ids: list[UUID] = Field(default_factory=list)
    compensation_authorized_user_ids: list[UUID] = Field(default_factory=list)
    # Only these approved category aliases are returned on the general dashboard.
    public_category_labels: dict[UUID,str] = Field(default_factory=dict)
    provider_labels: dict[UUID,str] = Field(default_factory=dict)
    fully_loaded_cost_coverage: dict[UUID,Coverage] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_access(self):
        if not set(self.compensation_authorized_user_ids)<=set(self.authorized_user_ids):
            raise ValueError("Compensation access requires general analytics access")
        if any(not value.strip() or len(value)>100 for mapping in (self.public_category_labels,self.provider_labels) for value in mapping.values()):
            raise ValueError("Display labels must contain 1–100 characters")
        return self

    def permits(self,uid,compensation=False):
        return UUID(str(uid)) in (self.compensation_authorized_user_ids if compensation else self.authorized_user_ids)

    def coverage(self):
        return {str(key):CostCoverage(value.start,value.end,value.basis) for key,value in self.fully_loaded_cost_coverage.items()}

def load_config(path):
    return AnalyticsConfig.model_validate_json(Path(path).read_text()) if path else AnalyticsConfig()
