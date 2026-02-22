import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock
import asyncio

@pytest.mark.anyio
async def test_webhook_crud(client):
    # Create module
    module_resp = await client.post("/modules", json={
        "name": "WebhookTestModule",
        "schema": {"type": "object", "properties": {"value": {"type": "integer"}}}
    })
    assert module_resp.status_code == 201
    module_id = module_resp.json()["id"]

    # Create Webhook
    webhook_data = {
        "url": "http://example.com/webhook",
        "module_id": module_id,
        "event_type": "event.created"
    }
    resp = await client.post("/webhooks", json=webhook_data)
    assert resp.status_code == 201
    webhook_id = resp.json()["id"]
    assert resp.json()["url"] == webhook_data["url"]

    # List Webhooks
    resp = await client.get("/webhooks")
    assert resp.status_code == 200
    webhooks = resp.json()
    assert len(webhooks) == 1
    assert webhooks[0]["id"] == webhook_id

    # Delete Webhook
    resp = await client.delete(f"/webhooks/{webhook_id}")
    assert resp.status_code == 204

    # List again
    resp = await client.get("/webhooks")
    assert resp.status_code == 200
    assert len(resp.json()) == 0

@pytest.mark.anyio
async def test_webhook_trigger(client):
    # Create module
    module_resp = await client.post("/modules", json={
        "name": "TriggerModule",
        "schema": {"type": "object", "properties": {"msg": {"type": "string"}}}
    })
    module_id = module_resp.json()["id"]

    # Register webhook
    webhook_url = "http://example.com/trigger"
    await client.post("/webhooks", json={
        "url": webhook_url,
        "module_id": module_id
    })

    # Patch app.main.httpx.AsyncClient so we don't affect the test client
    with patch("app.main.httpx.AsyncClient") as MockClient:
        mock_instance = MockClient.return_value
        # Setup async context manager
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None

        # Create event
        event_payload = {"msg": "hello"}
        resp = await client.post("/events", json={
            "module_id": module_id,
            "payload": event_payload
        })
        assert resp.status_code == 201

        # Allow background task to run
        await asyncio.sleep(0.1)

        # Verify call
        assert mock_instance.post.called
        args, kwargs = mock_instance.post.call_args
        assert args[0] == webhook_url
        assert kwargs["json"]["module_id"] == module_id
        assert kwargs["json"]["payload"] == event_payload
        assert kwargs["json"]["user_id"] is not None
        assert "timestamp" in kwargs["json"]

@pytest.mark.anyio
async def test_webhook_trigger_filter_mismatch(client):
    # Create module 1
    m1 = await client.post("/modules", json={"name": "M1", "schema": {}})
    mid1 = m1.json()["id"]

    # Create module 2
    m2 = await client.post("/modules", json={"name": "M2", "schema": {}})
    mid2 = m2.json()["id"]

    # Register webhook for M1
    webhook_url = "http://example.com/m1"
    await client.post("/webhooks", json={
        "url": webhook_url,
        "module_id": mid1
    })

    with patch("app.main.httpx.AsyncClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None

        # Create event for M2
        await client.post("/events", json={
            "module_id": mid2,
            "payload": {}
        })

        await asyncio.sleep(0.1)

        # Should NOT be called
        assert not mock_instance.post.called
