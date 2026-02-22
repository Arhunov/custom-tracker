import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta, timezone
from app.models import Event, Module

@pytest.mark.anyio
async def test_list_events_date_filter(client: AsyncClient, session, test_user):
    # Create module
    module = Module(name="filter_test_module", module_schema={"type": "object"})
    session.add(module)
    await session.commit()
    await session.refresh(module)

    # Create events with specific timestamps
    # Use timezone-aware datetimes
    now = datetime.now(timezone.utc)

    event1 = Event(user_id=test_user.id, module_id=module.id, payload={"data": 1}, timestamp=now - timedelta(days=10))
    event2 = Event(user_id=test_user.id, module_id=module.id, payload={"data": 2}, timestamp=now - timedelta(days=5))
    event3 = Event(user_id=test_user.id, module_id=module.id, payload={"data": 3}, timestamp=now - timedelta(days=1))

    session.add_all([event1, event2, event3])
    await session.commit()

    # Test filtering
    start_date = (now - timedelta(days=7)).isoformat()
    end_date = (now - timedelta(days=3)).isoformat()

    response = await client.get("/events", params={"start_date": start_date, "end_date": end_date})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["payload"]["data"] == 2

    # Test open-ended ranges
    start_date_only = (now - timedelta(days=7)).isoformat()
    response = await client.get("/events", params={"start_date": start_date_only})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2 # event2 and event3

    end_date_only = (now - timedelta(days=3)).isoformat()
    response = await client.get("/events", params={"end_date": end_date_only})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2 # event1 and event2

@pytest.mark.anyio
async def test_get_event_stats(client: AsyncClient, session, test_user):
    # Create modules
    mod1 = Module(name="stats_mod_1", module_schema={"type": "object"})
    mod2 = Module(name="stats_mod_2", module_schema={"type": "object"})
    session.add_all([mod1, mod2])
    await session.commit()
    await session.refresh(mod1)
    await session.refresh(mod2)

    # Create events
    events = [
        Event(user_id=test_user.id, module_id=mod1.id, payload={"v": 1}),
        Event(user_id=test_user.id, module_id=mod1.id, payload={"v": 2}),
        Event(user_id=test_user.id, module_id=mod1.id, payload={"v": 3}),
        Event(user_id=test_user.id, module_id=mod2.id, payload={"v": 4}),
    ]
    session.add_all(events)
    await session.commit()

    response = await client.get("/events/stats")
    assert response.status_code == 200
    data = response.json()

    # Sort data by module_id to ensure order
    data.sort(key=lambda x: x["module_id"])

    assert len(data) == 2
    assert data[0]["module_id"] == mod1.id
    assert data[0]["module_name"] == "stats_mod_1"
    assert data[0]["event_count"] == 3

    assert data[1]["module_id"] == mod2.id
    assert data[1]["module_name"] == "stats_mod_2"
    assert data[1]["event_count"] == 1

@pytest.mark.anyio
async def test_get_event_stats_date_filter(client: AsyncClient, session, test_user):
    mod = Module(name="stats_filter_mod", module_schema={"type": "object"})
    session.add(mod)
    await session.commit()
    await session.refresh(mod)

    now = datetime.now(timezone.utc)

    # event1: old
    event1 = Event(user_id=test_user.id, module_id=mod.id, payload={"v": 1}, timestamp=now - timedelta(days=10))
    # event2: recent
    event2 = Event(user_id=test_user.id, module_id=mod.id, payload={"v": 2}, timestamp=now - timedelta(days=1))

    session.add_all([event1, event2])
    await session.commit()

    # Filter for recent events
    start_date = (now - timedelta(days=5)).isoformat()
    response = await client.get("/events/stats", params={"start_date": start_date})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["module_id"] == mod.id
    assert data[0]["event_count"] == 1 # Only event2
