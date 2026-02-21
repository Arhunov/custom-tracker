from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any

# Placeholder schemas.
# Full definition depends on the content of AGENT.md which is currently missing.
# Please update these schemas once the requirements are clarified.

class EventBase(BaseModel):
    # Example field based on JSONB request
    data: Optional[Dict[str, Any]] = None

class EventCreate(EventBase):
    pass

class Event(EventBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class ModuleBase(BaseModel):
    # Example field based on JSONB request
    configuration: Optional[Dict[str, Any]] = None

class ModuleCreate(ModuleBase):
    pass

class Module(ModuleBase):
    id: int
    model_config = ConfigDict(from_attributes=True)
