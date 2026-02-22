import pytest
from httpx import AsyncClient

@pytest.mark.anyio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

@pytest.mark.anyio
async def test_create_module(client: AsyncClient):
    schema = {
        "type": "object",
        "properties": {
            "temperature": {"type": "number"},
            "unit": {"type": "string"}
        },
        "required": ["temperature"]
    }
    response = await client.post("/modules", json={"name": "weather", "schema": schema})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "weather"
    assert data["schema"] == schema
    assert "id" in data

@pytest.mark.anyio
async def test_create_module_duplicate(client: AsyncClient):
    schema = {"type": "object"}
    name = "weather_duplicate"
    await client.post("/modules", json={"name": name, "schema": schema})
    response = await client.post("/modules", json={"name": name, "schema": schema})
    assert response.status_code == 400

@pytest.mark.anyio
async def test_create_event(client: AsyncClient, test_user):
    # Capture user_id before API calls expire the session
    user_id = test_user.id

    # Create module first
    schema = {
        "type": "object",
        "properties": {
            "steps": {"type": "integer"}
        },
        "required": ["steps"]
    }
    mod_resp = await client.post("/modules", json={"name": "fitness", "schema": schema})
    assert mod_resp.status_code == 201
    module_id = mod_resp.json()["id"]

    # Create valid event
    payload = {"steps": 1000}
    response = await client.post("/events", json={"module_id": module_id, "payload": payload})
    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == user_id
    assert data["module_id"] == module_id
    assert data["payload"] == payload

    # Create invalid event (schema validation fail)
    bad_payload = {"steps": "many"} # string instead of integer
    response = await client.post("/events", json={"module_id": module_id, "payload": bad_payload})
    assert response.status_code == 400

@pytest.mark.anyio
async def test_list_events(client: AsyncClient, test_user):
    # Capture user_id
    user_id = test_user.id

    # Create module
    schema = {"type": "object"}
    mod_resp = await client.post("/modules", json={"name": "log", "schema": schema})
    module_id = mod_resp.json()["id"]

    # Create event
    await client.post("/events", json={"module_id": module_id, "payload": {}})

    response = await client.get("/events")
    assert response.status_code == 200
    assert len(response.json()) > 0

    # Filter
    response = await client.get(f"/events?user_id={user_id}")
    assert response.status_code == 200
    assert len(response.json()) >= 1
    assert response.json()[0]["user_id"] == user_id

@pytest.mark.anyio
async def test_unauthorized_access(client: AsyncClient):
    # Remove API Key header
    if "X-API-Key" in client.headers:
        del client.headers["X-API-Key"]

    response = await client.get("/modules")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing API Key"
