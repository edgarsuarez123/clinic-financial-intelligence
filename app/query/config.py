from pathlib import Path
from decimal import Decimal
from uuid import UUID
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel,ConfigDict,Field,model_validator,field_validator

class QueryConfig(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled: bool=False
    transport: Literal["https_chat","demo","ollama"]="https_chat"
    synthetic_data: bool=False
    authorized_user_ids: list[UUID]=Field(default_factory=list)
    cost_report_user_ids: list[UUID]=Field(default_factory=list)
    provider_name: str | None=None
    endpoint: str | None=None
    model: str | None=None
    disclosure_reference: str | None=None
    dpa_reference: str | None=None
    input_price_per_million: Decimal | None=Field(default=None,ge=0,le=Decimal("1000000"),allow_inf_nan=False)
    output_price_per_million: Decimal | None=Field(default=None,ge=0,le=Decimal("1000000"),allow_inf_nan=False)
    pricing_currency: str | None=Field(default=None,pattern='^[A-Z]{3}$')
    requests_per_window: int=Field(default=20,ge=1,le=1000)
    window_seconds: int=Field(default=3600,ge=60,le=86400)
    cache_seconds: int=Field(default=300,ge=1,le=3600)
    minimum_confidence: Decimal=Field(default=Decimal('0.9'),ge=Decimal('0.8'),le=1,allow_inf_nan=False)
    @field_validator('input_price_per_million','output_price_per_million',mode='before')
    @classmethod
    def exact_price(cls,value):
        if value is not None and not isinstance(value,(str,Decimal)): raise ValueError('Token prices must be decimal strings')
        return value
    @model_validator(mode='after')
    def configured(self):
        if not set(self.cost_report_user_ids)<=set(self.authorized_user_ids): raise ValueError('Cost report access requires query access')
        if self.endpoint:
            url=urlsplit(self.endpoint)
            if (url.scheme not in ({'http'} if self.transport=='ollama' else {'https'}) or not url.hostname or url.username or url.password or url.query or url.fragment):
                raise ValueError('LLM endpoint must be a configured HTTPS URL without credentials, query or fragment')
        if self.transport=='ollama':
            if not self.synthetic_data: raise ValueError('Ollama requires synthetic dev/test data')
            if self.model and ':cloud' in self.model.lower(): raise ValueError('Cloud models are not allowed for local Ollama')
            if not self.endpoint: raise ValueError('Ollama endpoint required')
            url=urlsplit(self.endpoint)
            if url.hostname not in {'localhost','127.0.0.1','::1','ollama','host.docker.internal'} or url.port!=11434 or url.path!='/api/chat':
                raise ValueError('Ollama must use an approved local host on port 11434 at /api/chat')
            if self.input_price_per_million!=0 or self.output_price_per_million!=0:
                raise ValueError('Local Ollama token prices must be zero; compute costs are not metered')
        if self.transport=="demo" and not self.synthetic_data: raise ValueError("Demo transport requires explicitly synthetic data")
        if self.enabled:
            if any(not value or not value.strip() for value in (self.provider_name,self.model,self.pricing_currency)):
                raise ValueError('Explicit provider label, model and pricing currency required')
            if self.input_price_per_million is None or self.output_price_per_million is None:
                raise ValueError('Explicit token pricing required')
        if self.transport=="demo" and (self.endpoint or self.input_price_per_million!=0 or self.output_price_per_million!=0):
            raise ValueError('Local demo requires no remote endpoint and zero token prices')
        if self.enabled and self.transport=="https_chat":
            if any(not value or not value.strip() for value in (self.provider_name,self.endpoint,self.model,self.disclosure_reference,self.dpa_reference,self.pricing_currency)):
                raise ValueError('Provider, model, written disclosure, DPA and pricing must be explicitly configured')
            if self.input_price_per_million is None or self.output_price_per_million is None: raise ValueError('Explicit token pricing required')
        return self
    def permits(self,uid): return self.enabled and UUID(str(uid)) in self.authorized_user_ids

def load_config(path): return QueryConfig.model_validate_json(Path(path).read_text()) if path else QueryConfig()
