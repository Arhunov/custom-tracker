from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any
from datetime import datetime

class ModuleBase(BaseModel):
    name: str
    module_schema: Dict[str, Any] = Field(..., alias="schema")

class ModuleCreate(ModuleBase):
    pass

class Module(ModuleBase):
    id: int
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class EventBase(BaseModel):
    module_id: int
    payload: Dict[str, Any]

class EventCreate(EventBase):
    pass

class Event(EventBase):
    id: int
    user_id: int
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)

class EventStats(BaseModel):
    module_id: int
    module_name: str
    event_count: int
    model_config = ConfigDict(from_attributes=True)
