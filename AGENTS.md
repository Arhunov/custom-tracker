# AGENT.md - Architecture for Custom Tracker

## Overview
A unified State Hub (Custom Tracker) to collect, store, and analyze human state data (sleep, food, weather, stress, etc.) without rigid silos. The focus is on a scalable, module-based architecture. Agents can interface with this API, but the primary purpose is providing a robust, extensible tracking backend.

## Architecture

**1. Core Event Stream**
- All data points are stored as a unified `Time-Series Event Log`.
- Fields: `id`, `user_id`, `timestamp`, `module_id`, `payload` (JSONB).
- Responsibilities: Authentication, Validation, Event storage.

**2. Module System (Marketplace concept)**
- Modules (e.g., Sleep, Food, Weather) define a `JSON Schema` for their expected payloads.
- The system registers these modules and validates incoming events against their schema before saving to the Core Event Stream.

**3. API (REST)**
- Written in Python (FastAPI).
- Endpoints for `POST /events` (with module_id and payload), `GET /events` (filtered by time range, module).
- Endpoints for `POST /modules` (register a new module schema), `GET /modules` (list available modules).

**4. Storage**
- PostgreSQL is the primary database, leveraging `JSONB` for the flexible payload structure.

## Technical Stack
- **Language:** Python 3
- **Framework:** FastAPI
- **Database:** PostgreSQL (with asyncpg / SQLAlchemy)
- **Validation:** Pydantic

## Rules for Jules
- When implementing features, strictly follow this architecture.
- Do not implement AI Analytics yet; focus on the Core Event Stream and Module System.
- **Provide a basic CLI interface** to interact with the system locally. This is crucial for me (the PM) and the Reviewer to test the APIs/business logic.
- Ensure all endpoints are documented (FastAPI does this automatically, but write clear docstrings).
- Write tests for the core logic (pytest).