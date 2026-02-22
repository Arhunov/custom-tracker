import pytest
from httpx import AsyncClient
from datetime import datetime, timezone

@pytest.mark.anyio
async def test_llm_context(client: AsyncClient, test_user):
    # 1. Create a module
    schema = {
        "type": "object",
        "properties": {
            "temperature": {"type": "number"},
            "unit": {"type": "string"}
        },
        "required": ["temperature"]
    }
    mod_resp = await client.post("/modules", json={"name": "weather_llm", "schema": schema})
    assert mod_resp.status_code == 201
    module_id = mod_resp.json()["id"]

    # 2. Create events
    payload1 = {"temperature": 22.5, "unit": "C"}
    resp1 = await client.post("/events", json={"module_id": module_id, "payload": payload1})
    assert resp1.status_code == 201

    payload2 = {"temperature": 23.0, "unit": "C"}
    resp2 = await client.post("/events", json={"module_id": module_id, "payload": payload2})
    assert resp2.status_code == 201

    # 3. Get LLM context
    response = await client.get("/llm/context")
    assert response.status_code == 200
    data = response.json()
    assert "context" in data

    context = data["context"]
    assert "weather_llm" in context
    assert "temperature=22.5" in context
    assert "temperature=23.0" in context

    # Check ordering (newest first)
    # "Newest first" means payload2 (created last) should appear before payload1
    idx1 = context.find("temperature=22.5")
    idx2 = context.find("temperature=23.0")
    assert idx2 < idx1

@pytest.mark.anyio
async def test_llm_context_filtering(client: AsyncClient, test_user):
    # Create module
    mod_resp = await client.post("/modules", json={"name": "steps_llm", "schema": {"type": "object"}})
    module_id = mod_resp.json()["id"]

    # Create event
    await client.post("/events", json={"module_id": module_id, "payload": {"steps": 100}})

    # Filter by module_id
    response = await client.get(f"/llm/context?module_id={module_id}")
    assert response.status_code == 200
    assert "steps_llm" in response.json()["context"]

    # Filter by wrong module_id
    response = await client.get(f"/llm/context?module_id={module_id + 999}")
    assert response.status_code == 200
    assert response.json()["context"] == ""

@pytest.mark.anyio
async def test_llm_context_unauthorized(client: AsyncClient):
    # Remove API Key
    if "X-API-Key" in client.headers:
        del client.headers["X-API-Key"]

    response = await client.get("/llm/context")
    assert response.status_code == 401
