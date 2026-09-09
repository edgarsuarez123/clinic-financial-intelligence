from pathlib import Path
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field
class SimulationConfig(BaseModel):
    model_config=ConfigDict(extra='forbid')
    authorized_user_ids: list[UUID] = Field(default_factory=list)
    synthetic_data: bool = False
    def permits(self,uid): return UUID(str(uid)) in self.authorized_user_ids
def load_config(path):
    return SimulationConfig.model_validate_json(Path(path).read_text()) if path else SimulationConfig()
