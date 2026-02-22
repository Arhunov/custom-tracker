import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app import models
import json
import csv
import io
import datetime

@pytest.mark.anyio
async def test_export_json(client: AsyncClient, session: AsyncSession, test_user):
    # Setup Module
    module_schema = {
        "type": "object",
        "properties": {
            "key": {"type": "string"}
        },
        "required": ["key"]
    }
    module = models.Module(name="Test Module Export JSON", module_schema=module_schema)
    session.add(module)
    await session.commit()
    await session.refresh(module)

    # Setup Event
    event = models.Event(
        user_id=test_user.id,
        module_id=module.id,
        payload={"key": "value"},
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)

    # Test Export
    response = await client.get("/data/export", params={"format": "json"})

    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    # Check if the event we created is in the export
    exported_event = next((e for e in data if e["id"] == event.id), None)
    assert exported_event is not None
    assert exported_event["payload"] == {"key": "value"}

@pytest.mark.anyio
async def test_export_csv(client: AsyncClient, session: AsyncSession, test_user):
    # Setup Module
    module_schema = {
        "type": "object",
        "properties": {
            "key": {"type": "string"}
        },
        "required": ["key"]
    }
    module = models.Module(name="Test Module Export CSV", module_schema=module_schema)
    session.add(module)
    await session.commit()
    await session.refresh(module)

    # Setup Event
    event = models.Event(
        user_id=test_user.id,
        module_id=module.id,
        payload={"key": "value"},
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)

    # Test Export
    response = await client.get("/data/export", params={"format": "csv"})

    assert response.status_code == 200
    content = response.content.decode("utf-8")

    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)

    assert len(rows) >= 1
    exported_event = next((row for row in rows if str(row["id"]) == str(event.id)), None)
    assert exported_event is not None
    assert json.loads(exported_event["payload"]) == {"key": "value"}

@pytest.mark.anyio
async def test_import_json(client: AsyncClient, session: AsyncSession, test_user):
    # Setup Module
    module_schema = {
        "type": "object",
        "properties": {
            "key": {"type": "string"}
        },
        "required": ["key"]
    }
    module = models.Module(name="Test Module Import JSON", module_schema=module_schema)
    session.add(module)
    await session.commit()
    await session.refresh(module)

    # Prepare Data
    import_data = [
        {
            "module_id": module.id,
            "payload": {"key": "imported_value"},
            "timestamp": "2023-01-01T12:00:00"
        }
    ]
    file_content = json.dumps(import_data).encode("utf-8")
    files = {"file": ("import.json", file_content, "application/json")}

    # Test Import
    response = await client.post("/data/import", files=files)

    assert response.status_code == 200
    result = response.json()
    assert result["success_count"] == 1
    assert result["failure_count"] == 0

    # Verify DB
    stmt = select(models.Event).where(models.Event.module_id == module.id)
    result = await session.execute(stmt)
    events = result.scalars().all()

    imported_event = next((e for e in events if e.payload.get("key") == "imported_value"), None)
    assert imported_event is not None

@pytest.mark.anyio
async def test_import_csv(client: AsyncClient, session: AsyncSession, test_user):
    # Setup Module
    module_schema = {
        "type": "object",
        "properties": {
            "key": {"type": "string"}
        },
        "required": ["key"]
    }
    module = models.Module(name="Test Module Import CSV", module_schema=module_schema)
    session.add(module)
    await session.commit()
    await session.refresh(module)

    # Prepare Data
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["module_id", "payload", "timestamp"])
    writer.writeheader()
    writer.writerow({
        "module_id": module.id,
        "payload": json.dumps({"key": "imported_csv_value"}),
        "timestamp": "2023-01-01T12:00:00"
    })
    file_content = output.getvalue().encode("utf-8")
    files = {"file": ("import.csv", file_content, "text/csv")}

    # Test Import
    response = await client.post("/data/import", files=files)

    assert response.status_code == 200
    result = response.json()
    assert result["success_count"] == 1
    assert result["failure_count"] == 0

    # Verify DB
    stmt = select(models.Event).where(models.Event.module_id == module.id)
    result = await session.execute(stmt)
    events = result.scalars().all()

    imported_event = next((e for e in events if e.payload.get("key") == "imported_csv_value"), None)
    assert imported_event is not None

@pytest.mark.anyio
async def test_import_invalid_schema(client: AsyncClient, session: AsyncSession, test_user):
    # Setup Module
    module_schema = {
        "type": "object",
        "properties": {
            "key": {"type": "integer"} # Expecting integer
        },
        "required": ["key"]
    }
    module = models.Module(name="Test Module Invalid Schema", module_schema=module_schema)
    session.add(module)
    await session.commit()
    await session.refresh(module)

    # Prepare Data with String (Invalid)
    import_data = [
        {
            "module_id": module.id,
            "payload": {"key": "invalid_value"},
            "timestamp": "2023-01-01T12:00:00"
        }
    ]
    file_content = json.dumps(import_data).encode("utf-8")
    files = {"file": ("import.json", file_content, "application/json")}

    # Test Import
    response = await client.post("/data/import", files=files)

    assert response.status_code == 200
    result = response.json()
    assert result["success_count"] == 0
    assert result["failure_count"] == 1
    assert len(result["errors"]) == 1
    assert "Row 0" in result["errors"][0]
