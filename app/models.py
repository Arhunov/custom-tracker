from sqlalchemy import Integer, String, DateTime, ForeignKey, Column, Boolean
from sqlalchemy.types import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional, Dict, Any
from .database import Base

# Use JSON type that supports JSONB on PostgreSQL and JSON on others (like SQLite for testing)
JSON_type = JSON().with_variant(JSONB, "postgresql")

class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    api_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class Module(Base):
    __tablename__ = 'modules'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    # The 'schema' field stores the JSON Schema for validation
    module_schema: Mapped[Dict[str, Any]] = mapped_column(JSON_type, name="schema")

class Event(Base):
    __tablename__ = 'events'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    module_id: Mapped[int] = mapped_column(ForeignKey('modules.id'))
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON_type)

    # Relationship to Module
    module: Mapped["Module"] = relationship()

class Webhook(Base):
    __tablename__ = 'webhooks'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    module_id: Mapped[Optional[int]] = mapped_column(ForeignKey('modules.id'), nullable=True)
    url: Mapped[str] = mapped_column(String)
    event_type: Mapped[str] = mapped_column(String, default="event.created")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    module: Mapped[Optional["Module"]] = relationship()
    user: Mapped["User"] = relationship()
