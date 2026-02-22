from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

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

class AggregationType(str, Enum):
    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"

class GroupBy(str, Enum):
    MODULE = "module"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"

class AggregationRequest(BaseModel):
    module_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    group_by: List[GroupBy] = []
    operation: AggregationType = AggregationType.COUNT
    target_key: Optional[str] = None # Key in JSON payload to aggregate on

class AggregationResult(BaseModel):
    group: Dict[str, Any]
    value: float | int

class CorrelationRequest(BaseModel):
    module_1_id: int
    target_1_key: str
    module_2_id: int
    target_2_key: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    group_by: GroupBy = GroupBy.DAY
    operation: AggregationType = AggregationType.AVG

class CorrelationResult(BaseModel):
    correlation_coefficient: Optional[float]
    data_points: int

class WebhookBase(BaseModel):
    module_id: Optional[int] = None
    url: HttpUrl
    event_type: str = "event.created"

class WebhookCreate(WebhookBase):
    pass

class Webhook(WebhookBase):
    id: int
    user_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
