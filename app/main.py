from fastapi import FastAPI, Depends, HTTPException, status, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from .database import get_db, engine, Base
from contextlib import asynccontextmanager
from . import models, schemas
from typing import List
import jsonschema
import os
import secrets

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_current_user(api_key: str = Security(api_key_header), db: AsyncSession = Depends(get_db)):
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API Key")

    stmt = select(models.User).where(models.User.api_key == api_key)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")

    return user

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default user
    async with AsyncSession(engine) as session:
        async with session.begin():
            stmt = select(models.User).limit(1)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if not user:
                admin_key = os.getenv("ADMIN_API_KEY")
                if not admin_key:
                    admin_key = secrets.token_urlsafe(32)
                    print(f"WARNING: ADMIN_API_KEY not set. Created admin user with key: {admin_key}")

                default_user = models.User(username="admin", api_key=admin_key)
                session.add(default_user)

    yield

app = FastAPI(title="Custom Tracker", lifespan=lifespan)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "database connected"}
    except Exception as e:
        return {"status": "database connection failed", "error": str(e)}

# Modules API

@app.post("/modules", response_model=schemas.Module, status_code=status.HTTP_201_CREATED)
async def create_module(
    module: schemas.ModuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Check if module with same name exists
    stmt = select(models.Module).where(models.Module.name == module.name)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Module with this name already exists")

    # Validate that the schema is a valid JSON schema
    try:
        jsonschema.Draft7Validator.check_schema(module.module_schema)
    except jsonschema.exceptions.SchemaError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON Schema: {e.message}")

    new_module = models.Module(name=module.name, module_schema=module.module_schema)
    db.add(new_module)
    await db.commit()
    await db.refresh(new_module)
    return new_module

@app.get("/modules", response_model=List[schemas.Module])
async def list_modules(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    stmt = select(models.Module).offset(skip).limit(limit)
    result = await db.execute(stmt)
    modules = result.scalars().all()
    return modules

# Events API

@app.post("/events", response_model=schemas.Event, status_code=status.HTTP_201_CREATED)
async def create_event(
    event: schemas.EventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Fetch the module to get the schema
    stmt = select(models.Module).where(models.Module.id == event.module_id)
    result = await db.execute(stmt)
    module = result.scalar_one_or_none()

    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    # Validate payload against module schema
    try:
        jsonschema.validate(instance=event.payload, schema=module.module_schema)
    except jsonschema.exceptions.ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Payload validation failed: {e.message}")

    new_event = models.Event(
        user_id=current_user.id,
        module_id=event.module_id,
        payload=event.payload
    )
    db.add(new_event)
    await db.commit()
    await db.refresh(new_event)
    return new_event

@app.get("/events", response_model=List[schemas.Event])
async def list_events(
    skip: int = 0,
    limit: int = 100,
    module_id: int | None = None,
    user_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    stmt = select(models.Event)
    if module_id:
        stmt = stmt.where(models.Event.module_id == module_id)
    if user_id:
        stmt = stmt.where(models.Event.user_id == user_id)

    stmt = stmt.order_by(models.Event.timestamp.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    events = result.scalars().all()
    return events
