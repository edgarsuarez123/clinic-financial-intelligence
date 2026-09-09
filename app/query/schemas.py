from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field

class Model(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Question(Model):
    question: str=Field(min_length=1,max_length=1000)
    start: date
    end: date
    allow_provider_data: bool=False
    acknowledge_external_processing: Literal[True]
class Translation(Model):
    answerable: bool
    confidence: Decimal=Field(ge=0,le=1,allow_inf_nan=False)
    query_key: str=Field(max_length=50)
    sql: str=Field(max_length=6000)
    parameters: dict[str,str]
class Fact(Model):
    row: int=Field(strict=True,ge=0,le=99)
    column: str=Field(max_length=50)
class Explanation(Model):
    facts: list[Fact]=Field(min_length=1,max_length=20)
