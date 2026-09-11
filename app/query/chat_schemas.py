from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Model(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)

class Context(Model):
    start: date
    end: date
    clinic_location: str | None = Field(default=None,max_length=100)
    budget_ids: list[UUID] = Field(default_factory=list,max_length=3)
    @model_validator(mode='after')
    def dates(self):
        from ..analytics.calculations import check_range
        check_range(self.start,self.end)
        if len(set(self.budget_ids))!=len(self.budget_ids): raise ValueError('Choose distinct plans')
        return self

class ConversationCreate(Model):
    conversation_id: UUID
    title: str = Field(default='New conversation',min_length=1,max_length=100)

class Revision(Model):
    expected_revision: int = Field(strict=True,ge=1)

class Rename(Revision):
    title: str = Field(min_length=1,max_length=100)

class Turn(Revision):
    turn_id: UUID
    question: str = Field(min_length=1,max_length=2000)
    context: Context

class Change(Model):
    kind: Literal['revenue_percent','cost_percent','salary_percent','driver_units_percent','driver_payment_percent','staff_start']
    row_index: int = Field(default=0,strict=True,ge=0,le=49)
    from_month: int = Field(default=1,strict=True,ge=1,le=120)
    through_month: int = Field(default=120,strict=True,ge=1,le=120)
    percent: Decimal = Field(default=Decimal('0'),ge=-100,le=200,allow_inf_nan=False)

class ChatSelection(Model):
    tool: Literal['analytics','scenarios','what_if','forecast','clarify']
    query_key: str = Field(default='monthly',max_length=50)
    budget_ids: list[UUID] = Field(default_factory=list,max_length=3)
    changes: list[Change] = Field(default_factory=list,max_length=12)
    horizon: int = Field(default=6,strict=True,ge=1,le=12)
    confidence: Decimal = Field(ge=0,le=1)
    clarification: str = Field(default='',max_length=400)
    recommendations: bool = False
    visualization: Literal['auto','table','line','bar'] = 'auto'

class Inference(Model):
    text: str = Field(min_length=1,max_length=1000)
    evidence: list[str] = Field(min_length=1,max_length=8)

class ChatNarrative(Model):
    interpretation: list[Inference] = Field(default_factory=list,max_length=3)
    recommendations: list[Inference] = Field(default_factory=list,max_length=3)
