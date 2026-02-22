import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta

@pytest.mark.anyio
async def test_aggregate_by_module(client: AsyncClient, test_user):
    # Setup
    schema = {"type": "object"}
    mod1 = await client.post("/modules", json={"name": "mod1", "schema": schema})
    mod2 = await client.post("/modules", json={"name": "mod2", "schema": schema})

    assert mod1.status_code == 201
    assert mod2.status_code == 201

    id1 = mod1.json()["id"]
    id2 = mod2.json()["id"]

    # Create events
    await client.post("/events", json={"module_id": id1, "payload": {"val": 10}})
    await client.post("/events", json={"module_id": id1, "payload": {"val": 20}})
    await client.post("/events", json={"module_id": id2, "payload": {"val": 30}})

    # Test Group By Module
    resp = await client.post("/analytics/aggregate", json={
        "group_by": ["module"],
        "operation": "count"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    # Sort to verify
    data.sort(key=lambda x: x["group"]["module_id"])
    assert data[0]["group"]["module_id"] == id1
    assert data[0]["value"] == 2
    assert data[1]["group"]["module_id"] == id2
    assert data[1]["value"] == 1

@pytest.mark.anyio
async def test_aggregate_sum(client: AsyncClient, test_user):
    # Setup
    schema = {"type": "object"}
    mod = await client.post("/modules", json={"name": "math", "schema": schema})
    assert mod.status_code == 201
    mid = mod.json()["id"]

    await client.post("/events", json={"module_id": mid, "payload": {"score": 10}})
    await client.post("/events", json={"module_id": mid, "payload": {"score": 20}})
    await client.post("/events", json={"module_id": mid, "payload": {"score": 30}})

    # Test Sum
    resp = await client.post("/analytics/aggregate", json={
        "module_id": mid,
        "operation": "sum",
        "target_key": "score"
    })

    assert resp.status_code == 200
    data = resp.json()
    # No grouping, so 1 result
    assert len(data) == 1
    assert data[0]["value"] == 60

@pytest.mark.anyio
async def test_aggregate_missing_key_error(client: AsyncClient, test_user):
    # Test that SUM without target_key returns 400
    resp = await client.post("/analytics/aggregate", json={
        "operation": "sum"
        # missing target_key
    })
    assert resp.status_code == 400
    assert "target_key is required" in resp.json()["detail"]

@pytest.mark.anyio
async def test_aggregate_by_date(client: AsyncClient, test_user):
    # Since we can't easily force timestamps in create_event (server sets it),
    # we just test that grouping by day works and returns the current day bucket.

    schema = {"type": "object"}
    mod = await client.post("/modules", json={"name": "daily", "schema": schema})
    mid = mod.json()["id"]

    await client.post("/events", json={"module_id": mid, "payload": {}})
    await client.post("/events", json={"module_id": mid, "payload": {}})

    # Test Group By Day
    resp = await client.post("/analytics/aggregate", json={
        "group_by": ["day"],
        "operation": "count"
    })

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    # Check key exists
    assert "date_day" in data[0]["group"]
    assert data[0]["value"] >= 2
