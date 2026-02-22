from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any
from datetime import datetime

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

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
