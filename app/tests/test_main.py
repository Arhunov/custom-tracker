import pytest
from httpx import AsyncClient

@pytest.mark.anyio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

@pytest.mark.anyio
async def test_create_module(client: AsyncClient, auth_headers):
    schema = {
        "type": "object",
        "properties": {
            "temperature": {"type": "number"},
            "unit": {"type": "string"}
        },
        "required": ["temperature"]
    }
    response = await client.post("/modules", json={"name": "weather", "schema": schema}, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "weather"
    assert data["schema"] == schema
    assert "id" in data

@pytest.mark.anyio
async def test_create_module_duplicate(client: AsyncClient, auth_headers):
    schema = {"type": "object"}
    name = "weather_duplicate"
    await client.post("/modules", json={"name": name, "schema": schema}, headers=auth_headers)
    response = await client.post("/modules", json={"name": name, "schema": schema}, headers=auth_headers)
    assert response.status_code == 400

@pytest.mark.anyio
async def test_create_event(client: AsyncClient, auth_headers):
    # Create module first
    schema = {
        "type": "object",
        "properties": {
            "steps": {"type": "integer"}
        },
        "required": ["steps"]
    }
    mod_resp = await client.post("/modules", json={"name": "fitness", "schema": schema}, headers=auth_headers)
    assert mod_resp.status_code == 201
    module_id = mod_resp.json()["id"]

    # Create valid event
    payload = {"steps": 1000}
    # Note: user_id is NOT sent, but is inferred from auth_headers
    response = await client.post("/events", json={"module_id": module_id, "payload": payload}, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    # The user created in auth_headers will have ID 1 usually (since it's fresh DB)
    assert data["user_id"] is not None
    assert data["module_id"] == module_id
    assert data["payload"] == payload

    # Create invalid event (schema validation fail)
    bad_payload = {"steps": "many"} # string instead of integer
    response = await client.post("/events", json={"module_id": module_id, "payload": bad_payload}, headers=auth_headers)
    assert response.status_code == 400

@pytest.mark.anyio
async def test_list_events(client: AsyncClient, auth_headers):
    # Create module
    schema = {"type": "object"}
    mod_resp = await client.post("/modules", json={"name": "log", "schema": schema}, headers=auth_headers)
    module_id = mod_resp.json()["id"]

    # Create event
    await client.post("/events", json={"module_id": module_id, "payload": {}}, headers=auth_headers)

    response = await client.get("/events", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) > 0

    # Filter
    # Need to know the user_id. The auth_headers user is likely ID 1.
    # We can get it from the event we just created.
    events = response.json()
    user_id = events[0]["user_id"]

    response = await client.get(f"/events?user_id={user_id}", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1
    assert response.json()[0]["user_id"] == user_id

@pytest.mark.anyio
async def test_list_modules(client: AsyncClient, auth_headers):
    # Create module
    schema = {"type": "object"}
    await client.post("/modules", json={"name": "list_test", "schema": schema}, headers=auth_headers)

    response = await client.get("/modules", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) > 0

    # Test unauthorized access
    response = await client.get("/modules")
    assert response.status_code == 401
