from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from .database import get_db, engine, Base
from contextlib import asynccontextmanager
from . import models, schemas, auth
from typing import List
import jsonschema
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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

@app.post("/register", response_model=schemas.User, status_code=status.HTTP_201_CREATED)
async def register_user(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    stmt = select(models.User).where(models.User.username == user.username)
    result = await db.execute(stmt)
    db_user = result.scalar_one_or_none()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(username=user.username, hashed_password=hashed_password)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    stmt = select(models.User).where(models.User.username == form_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# Modules API

@app.post("/modules", response_model=schemas.Module, status_code=status.HTTP_201_CREATED)
async def create_module(module: schemas.ModuleCreate, db: AsyncSession = Depends(get_db), current_user: schemas.User = Depends(auth.get_current_user)):
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
async def list_modules(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db), current_user: schemas.User = Depends(auth.get_current_user)):
    stmt = select(models.Module).offset(skip).limit(limit)
    result = await db.execute(stmt)
    modules = result.scalars().all()
    return modules

# Events API

@app.post("/events", response_model=schemas.Event, status_code=status.HTTP_201_CREATED)
async def create_event(event: schemas.EventCreate, db: AsyncSession = Depends(get_db), current_user: schemas.User = Depends(auth.get_current_user)):
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
    current_user: schemas.User = Depends(auth.get_current_user)
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
