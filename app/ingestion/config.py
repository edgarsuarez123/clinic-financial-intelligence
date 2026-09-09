import hashlib
import json
from pathlib import Path
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    columns: dict[str, str]
    date_format: Literal["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]
    types: dict[str, Literal["revenue", "expense"]]
    categories: dict[str, UUID]
    providers: dict[str, UUID]
    delimiter: str = Field(default=",", min_length=1, max_length=1)
    pdf_strategy: Literal["lines", "text"] = "lines"
    allow_negative_amounts: bool
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def validate_mapping(self):
        if set(self.columns) != {"date", "amount", "type", "category", "provider"}:
            raise ValueError("Map each of the five canonical columns explicitly")
        if len(set(self.columns.values())) != 5 or any(not v or len(v)>100 for v in self.columns.values()):
            raise ValueError("Source headers must be distinct, nonempty and at most 100 characters")
        if not self.types or not self.categories:
            raise ValueError("Explicit type and category mappings are required")
        if any(not k or len(k)>256 for mapping in (self.types,self.categories,self.providers) for k in mapping):
            raise ValueError("Invalid mapping label")
        return self

    def digest(self):
        return hashlib.sha256(json.dumps(self.model_dump(mode="json"),sort_keys=True).encode()).hexdigest()

class IngestionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    mode: Literal["disabled", "synthetic", "clinic"] = "disabled"
    no_phi_confirmed: bool = False
    authorized_user_ids: list[UUID] = Field(default_factory=list)
    profiles: dict[str, Profile] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ready(self):
        if self.mode != "disabled" and (not self.no_phi_confirmed or not self.authorized_user_ids or not self.profiles):
            raise ValueError("Enabled ingestion requires explicit scope, users and mappings")
        if len({v.currency for v in self.profiles.values()}) > 1:
            raise ValueError("One explicitly configured currency per isolated clinic")
        return self

    def permits(self, uid):
        return self.mode != "disabled" and UUID(str(uid)) in self.authorized_user_ids

def load_config(path):
    return IngestionConfig.model_validate_json(Path(path).read_text()) if path else IngestionConfig()
