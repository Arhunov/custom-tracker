from fastapi import FastAPI, Depends, HTTPException, status, Security, UploadFile, File, BackgroundTasks
from fastapi.security import APIKeyHeader
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func, cast, Numeric, or_
from sqlalchemy.orm import selectinload
from .database import get_db, engine, Base
from contextlib import asynccontextmanager
from . import models, schemas
from typing import List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy import func
import jsonschema
import os
import secrets
import csv
import io
import json
import httpx
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Webhooks API

@app.post("/webhooks", response_model=schemas.Webhook, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    webhook: schemas.WebhookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # If module_id is provided, verify it exists
    if webhook.module_id:
        stmt = select(models.Module).where(models.Module.id == webhook.module_id)
        result = await db.execute(stmt)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Module not found")

    new_webhook = models.Webhook(
        user_id=current_user.id,
        module_id=webhook.module_id,
        url=str(webhook.url),
        event_type=webhook.event_type
    )
    db.add(new_webhook)
    await db.commit()
    await db.refresh(new_webhook)
    return new_webhook

@app.get("/webhooks", response_model=List[schemas.Webhook])
async def list_webhooks(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    stmt = select(models.Webhook).where(models.Webhook.user_id == current_user.id).offset(skip).limit(limit)
    result = await db.execute(stmt)
    webhooks = result.scalars().all()
    return webhooks

@app.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    stmt = select(models.Webhook).where(models.Webhook.id == webhook_id, models.Webhook.user_id == current_user.id)
    result = await db.execute(stmt)
    webhook = result.scalar_one_or_none()

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    await db.delete(webhook)
    await db.commit()

async def trigger_webhooks(event_id: int, module_id: int, user_id: int, payload: Dict[str, Any]):
    try:
        async with AsyncSession(engine) as session:
            # Find webhooks: belonging to the user AND (module_id matches OR module_id is null)
            stmt = select(models.Webhook).where(
                models.Webhook.user_id == user_id,
                or_(models.Webhook.module_id == module_id, models.Webhook.module_id.is_(None))
            )
            result = await session.execute(stmt)
            webhooks = result.scalars().all()

            if not webhooks:
                return

            async with httpx.AsyncClient() as client:
                for webhook in webhooks:
                    try:
                        data = {
                            "event_id": event_id,
                            "module_id": module_id,
                            "user_id": user_id,
                            "payload": payload,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "event_type": webhook.event_type
                        }
                        await client.post(webhook.url, json=data, timeout=5.0)
                    except Exception as e:
                        logger.error(f"Failed to trigger webhook {webhook.id} to {webhook.url}: {e}")
    except Exception as e:
        logger.error(f"Error in trigger_webhooks: {e}")

# Events API

@app.post("/events", response_model=schemas.Event, status_code=status.HTTP_201_CREATED)
async def create_event(
    event: schemas.EventCreate,
    background_tasks: BackgroundTasks,
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

    background_tasks.add_task(
        trigger_webhooks,
        event_id=new_event.id,
        module_id=new_event.module_id,
        user_id=new_event.user_id,
        payload=new_event.payload
    )

    return new_event

@app.get("/events/stats", response_model=List[schemas.EventStats])
async def get_event_stats(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    stmt = select(
        models.Module.id.label("module_id"),
        models.Module.name.label("module_name"),
        func.count(models.Event.id).label("event_count")
    ).join(models.Event, models.Module.id == models.Event.module_id)

    if start_date:
        stmt = stmt.where(models.Event.timestamp >= start_date)
    if end_date:
        stmt = stmt.where(models.Event.timestamp <= end_date)

    stmt = stmt.group_by(models.Module.id, models.Module.name)

    result = await db.execute(stmt)
    return result.all()

@app.get("/events", response_model=List[schemas.Event])
async def list_events(
    skip: int = 0,
    limit: int = 100,
    module_id: int | None = None,
    user_id: int | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    stmt = select(models.Event)
    if module_id:
        stmt = stmt.where(models.Event.module_id == module_id)
    if user_id:
        stmt = stmt.where(models.Event.user_id == user_id)
    if start_date:
        stmt = stmt.where(models.Event.timestamp >= start_date)
    if end_date:
        stmt = stmt.where(models.Event.timestamp <= end_date)

    stmt = stmt.order_by(models.Event.timestamp.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    events = result.scalars().all()
    return events

# Analytics API

async def get_time_series_data(
    db: AsyncSession,
    module_id: int,
    target_key: str,
    start_date: datetime | None,
    end_date: datetime | None,
    group_by: schemas.GroupBy,
    operation: schemas.AggregationType
) -> Dict[str, float]:
    select_clauses = []
    group_by_clauses = []

    # Detect dialect for date truncation and JSON extraction compatibility (SQLite vs Postgres)
    # Default to postgresql logic unless we detect sqlite
    dialect_name = "postgresql"
    if db.bind and hasattr(db.bind, "dialect"):
         dialect_name = db.bind.dialect.name
    # Handle the case where bind might be an engine or connection wrapper
    # In tests with aiosqlite, dialect is sqlite

    # 1. Group By Logic (Time only)
    col = None
    if dialect_name == "postgresql":
        trunc_unit = group_by.value
        col = func.date_trunc(trunc_unit, models.Event.timestamp).label(f"date_{trunc_unit}")
    else:
        # SQLite fallback
        if group_by == schemas.GroupBy.DAY:
            fmt = "%Y-%m-%d"
        elif group_by == schemas.GroupBy.MONTH:
            fmt = "%Y-%m"
        elif group_by == schemas.GroupBy.WEEK:
            fmt = "%Y-%W"
        else:
            fmt = "%Y-%m-%d"

        col = func.strftime(fmt, models.Event.timestamp).label(f"date_{group_by.value}")

    select_clauses.append(col)
    group_by_clauses.append(col)

    # 2. Aggregation Logic
    field_expr = None
    if dialect_name == "postgresql":
            # Postgres: payload ->> key, cast to Numeric
            field_expr = cast(models.Event.payload[target_key].astext, Numeric)
    else:
            # SQLite: json_extract
            field_expr = func.json_extract(models.Event.payload, f"$.{target_key}")

    agg_func = None
    if operation == schemas.AggregationType.SUM:
        agg_func = func.sum(field_expr)
    elif operation == schemas.AggregationType.AVG:
        agg_func = func.avg(field_expr)
    elif operation == schemas.AggregationType.MIN:
        agg_func = func.min(field_expr)
    elif operation == schemas.AggregationType.MAX:
        agg_func = func.max(field_expr)
    else:
        agg_func = func.count(models.Event.id) # Fallback

    select_clauses.append(agg_func.label("value"))

    stmt = select(*select_clauses)
    stmt = stmt.where(models.Event.module_id == module_id)

    if start_date:
        stmt = stmt.where(models.Event.timestamp >= start_date)
    if end_date:
        stmt = stmt.where(models.Event.timestamp <= end_date)

    stmt = stmt.group_by(*group_by_clauses)

    result = await db.execute(stmt)
    rows = result.all()

    # Convert to dictionary {date_str: value}
    data = {}
    for row in rows:
        # The first column is the date string/object (depends on dialect/driver)
        # The second column is the value

        date_val = row[0]
        val = row[1]

        key = None
        if hasattr(date_val, "isoformat"):
            key = date_val.isoformat()
        else:
            key = str(date_val)

        data[key] = float(val) if val is not None else 0.0

    return data

@app.post("/analytics/aggregate", response_model=List[schemas.AggregationResult])
async def aggregate_events(
    request: schemas.AggregationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    select_clauses = []
    group_by_clauses = []

    # Detect dialect for date truncation and JSON extraction compatibility (SQLite vs Postgres)
    # Default to postgresql logic unless we detect sqlite
    dialect_name = "postgresql"
    if db.bind and hasattr(db.bind, "dialect"):
         dialect_name = db.bind.dialect.name
    # Handle the case where bind might be an engine or connection wrapper
    # In tests with aiosqlite, dialect is sqlite

    # 1. Group By Logic
    for group in request.group_by:
        if group == schemas.GroupBy.MODULE:
            select_clauses.append(models.Event.module_id.label("module_id"))
            group_by_clauses.append(models.Event.module_id)
        elif group in [schemas.GroupBy.DAY, schemas.GroupBy.WEEK, schemas.GroupBy.MONTH]:
            if dialect_name == "postgresql":
                trunc_unit = group.value
                col = func.date_trunc(trunc_unit, models.Event.timestamp).label(f"date_{trunc_unit}")
                select_clauses.append(col)
                group_by_clauses.append(col)
            else:
                # SQLite fallback
                if group == schemas.GroupBy.DAY:
                    fmt = "%Y-%m-%d"
                elif group == schemas.GroupBy.MONTH:
                    fmt = "%Y-%m"
                elif group == schemas.GroupBy.WEEK:
                    fmt = "%Y-%W"
                else:
                    fmt = "%Y-%m-%d"

                col = func.strftime(fmt, models.Event.timestamp).label(f"date_{group.value}")
                select_clauses.append(col)
                group_by_clauses.append(col)

    # 2. Aggregation Logic
    agg_func = None

    # Validation: Ensure target_key is provided for operations that require it
    if request.operation in [schemas.AggregationType.SUM, schemas.AggregationType.AVG, schemas.AggregationType.MIN, schemas.AggregationType.MAX]:
        if not request.target_key:
            raise HTTPException(status_code=400, detail="target_key is required for aggregation operations other than COUNT")

    # Extract value if target_key is provided
    field_expr = None
    if request.target_key:
        if dialect_name == "postgresql":
             # Postgres: payload ->> key, cast to Numeric
             # Using models.Event.payload[key].astext is standard SQLAlchemy for JSONB
             field_expr = cast(models.Event.payload[request.target_key].astext, Numeric)
        else:
             # SQLite: json_extract
             field_expr = func.json_extract(models.Event.payload, f"$.{request.target_key}")

    if request.operation == schemas.AggregationType.COUNT:
        agg_func = func.count(models.Event.id)
    elif field_expr is not None:
        if request.operation == schemas.AggregationType.SUM:
            agg_func = func.sum(field_expr)
        elif request.operation == schemas.AggregationType.AVG:
            agg_func = func.avg(field_expr)
        elif request.operation == schemas.AggregationType.MIN:
            agg_func = func.min(field_expr)
        elif request.operation == schemas.AggregationType.MAX:
            agg_func = func.max(field_expr)

    # Fallback/Default
    if agg_func is None:
         agg_func = func.count(models.Event.id)

    select_clauses.append(agg_func.label("value"))

    # Build Statement
    stmt = select(*select_clauses)

    # 3. Filtering
    if request.module_id:
        stmt = stmt.where(models.Event.module_id == request.module_id)
    if request.start_date:
        stmt = stmt.where(models.Event.timestamp >= request.start_date)
    if request.end_date:
        stmt = stmt.where(models.Event.timestamp <= request.end_date)

    # 4. Apply Group By
    if group_by_clauses:
        stmt = stmt.group_by(*group_by_clauses)

    result = await db.execute(stmt)
    rows = result.all()

    # 5. Format Output
    output = []
    for row in rows:
        row_dict = row._mapping

        group_dict = {}
        for key, val in row_dict.items():
            if key == "value":
                continue
            group_dict[key] = val

        output.append(schemas.AggregationResult(
            group=group_dict,
            value=row_dict["value"] or 0
        ))

    return output

@app.post("/analytics/correlation", response_model=schemas.CorrelationResult)
async def calculate_correlation(
    request: schemas.CorrelationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Fetch data for module 1
    data1 = await get_time_series_data(
        db,
        request.module_1_id,
        request.target_1_key,
        request.start_date,
        request.end_date,
        request.group_by,
        request.operation
    )

    # Fetch data for module 2
    data2 = await get_time_series_data(
        db,
        request.module_2_id,
        request.target_2_key,
        request.start_date,
        request.end_date,
        request.group_by,
        request.operation
    )

    # Align data
    common_keys = set(data1.keys()) & set(data2.keys())

    if len(common_keys) < 2:
        return schemas.CorrelationResult(correlation_coefficient=None, data_points=len(common_keys))

    x = []
    y = []
    for key in common_keys:
        x.append(data1[key])
        y.append(data2[key])

    # Calculate Pearson Correlation
    n = len(x)
    sum_x = sum(x)
    sum_y = sum(y)
    sum_x_sq = sum(val**2 for val in x)
    sum_y_sq = sum(val**2 for val in y)
    sum_xy = sum(x[i] * y[i] for i in range(n))

    numerator = (n * sum_xy) - (sum_x * sum_y)
    denominator_sq = ((n * sum_x_sq) - (sum_x**2)) * ((n * sum_y_sq) - (sum_y**2))

    if denominator_sq <= 0:
        return schemas.CorrelationResult(correlation_coefficient=None, data_points=n)

    denominator = denominator_sq ** 0.5
    correlation = numerator / denominator

    return schemas.CorrelationResult(correlation_coefficient=correlation, data_points=n)


# Data Export API

@app.get("/data/export")
async def export_data(
    format: str = "json",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    module_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if format not in ["json", "csv"]:
        raise HTTPException(status_code=400, detail="Invalid format. Supported formats: json, csv")

    stmt = select(models.Event)
    if module_id:
        stmt = stmt.where(models.Event.module_id == module_id)
    if start_date:
        stmt = stmt.where(models.Event.timestamp >= start_date)
    if end_date:
        stmt = stmt.where(models.Event.timestamp <= end_date)

    # Ensure consistent ordering
    stmt = stmt.order_by(models.Event.timestamp.desc())

    result = await db.execute(stmt)
    events = result.scalars().all()

    if format == "json":
        data = [schemas.Event.model_validate(event).model_dump(mode='json') for event in events]

        # Use a generator to stream JSON response
        def iter_json():
            yield json.dumps(data)

        return StreamingResponse(iter_json(), media_type="application/json", headers={"Content-Disposition": "attachment; filename=export.json"})

    elif format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)

        # Define headers
        headers = ["id", "user_id", "module_id", "timestamp", "payload"]
        writer.writerow(headers)

        # Write data to StringIO buffer
        for event in events:
            writer.writerow([
                event.id,
                event.user_id,
                event.module_id,
                event.timestamp.isoformat(),
                json.dumps(event.payload)
            ])

        output.seek(0)
        return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=export.csv"})


# Data Import API

@app.post("/data/import")
async def import_data(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Determine format
    filename = file.filename.lower()
    if filename.endswith(".json"):
        format = "json"
    elif filename.endswith(".csv"):
        format = "csv"
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format. Use .json or .csv")

    content = await file.read()

    events_to_create = []

    if format == "json":
        try:
            data = json.loads(content.decode("utf-8"))
            if not isinstance(data, list):
                raise ValueError("JSON content must be a list of events")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON file")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        for item in data:
            events_to_create.append(item)

    elif format == "csv":
        try:
            decoded_content = content.decode("utf-8")
            reader = csv.DictReader(io.StringIO(decoded_content))
            for row in reader:
                # payload is stored as JSON string in CSV
                if "payload" in row:
                    try:
                        row["payload"] = json.loads(row["payload"])
                    except json.JSONDecodeError:
                         raise HTTPException(status_code=400, detail="Invalid JSON in CSV payload column")

                events_to_create.append(row)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error parsing CSV: {str(e)}")

    success_count = 0
    failure_count = 0
    errors = []

    # Get all modules to validate schemas
    stmt = select(models.Module)
    result = await db.execute(stmt)
    modules = {m.id: m for m in result.scalars().all()}

    for i, event_data in enumerate(events_to_create):
        try:
            module_id = int(event_data.get("module_id"))
            if module_id not in modules:
                raise ValueError(f"Module ID {module_id} not found")

            module = modules[module_id]
            payload = event_data.get("payload", {})

            # Validate schema
            jsonschema.validate(instance=payload, schema=module.module_schema)

            timestamp = event_data.get("timestamp")
            if timestamp:
                 # Ensure timestamp is parsed correctly if it's a string
                 if isinstance(timestamp, str):
                     timestamp = datetime.fromisoformat(timestamp)
            else:
                timestamp = datetime.utcnow()

            user_id = event_data.get("user_id")
            if not user_id:
                user_id = current_user.id
            else:
                user_id = int(user_id)

            new_event = models.Event(
                user_id=user_id,
                module_id=module_id,
                timestamp=timestamp,
                payload=payload
            )
            db.add(new_event)
            success_count += 1

        except Exception as e:
            failure_count += 1
            errors.append(f"Row {i}: {str(e)}")

    await db.commit()

    return {
        "status": "completed",
        "success_count": success_count,
        "failure_count": failure_count,
        "errors": errors[:10] # Limit error details
    }

# LLM Context API

@app.get("/llm/context", response_model=Dict[str, str])
async def get_llm_context(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    module_id: int | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    stmt = select(models.Event).options(selectinload(models.Event.module))
    stmt = stmt.where(models.Event.user_id == current_user.id)

    if module_id:
        stmt = stmt.where(models.Event.module_id == module_id)
    if start_date:
        stmt = stmt.where(models.Event.timestamp >= start_date)
    if end_date:
        stmt = stmt.where(models.Event.timestamp <= end_date)

    stmt = stmt.order_by(models.Event.timestamp.desc(), models.Event.id.desc()).limit(limit)

    result = await db.execute(stmt)
    events = result.scalars().all()

    formatted_lines = []
    for event in events:
        module_name = event.module.name if event.module else "Unknown"
        timestamp_str = event.timestamp.isoformat()

        payload_items = []
        if isinstance(event.payload, dict):
            for k, v in event.payload.items():
                payload_items.append(f"{k}={v}")
        else:
            payload_items.append(str(event.payload))

        payload_str = ", ".join(payload_items)

        formatted_lines.append(f"[{timestamp_str}] {module_name}: {payload_str}")

    return {"context": "\n".join(formatted_lines)}
