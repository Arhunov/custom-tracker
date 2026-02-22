# AGENTS.md - Sprint Planning & Reviewer Context

## Project: Custom Tracker
**Goal:** Create a unified state tracking backend that handles dynamic modules via a Time-Series Event Log with JSONB payloads.

## Current Sprint Tasks
1. **Initialize Project & Database Structure:** Setup FastAPI, PostgreSQL connection, and the base `Event` and `Module` tables.
2. **Implement Module Registration API:** Endpoints to register schemas for different trackers.
3. **Implement Event Stream API:** Endpoints to submit and retrieve tracker events, validated against the module schemas.
4. **Basic Authentication:** Simple user auth to secure the API.
5. **CLI Interface:** A basic CLI tool to interact with the API (for me and the Reviewer to test easily).

## Reviewer Guidelines
- Strictly check for architectural alignment (FastAPI, PostgreSQL JSONB).
- Ensure Pydantic is used for validating incoming event payloads against registered module schemas.
- Look for security flaws (e.g., lack of auth on core endpoints) and code smells.
- Provide targeted comments on the PR. Only focus on the implemented scope of the PR.