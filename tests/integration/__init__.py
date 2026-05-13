"""
Integration and end-to-end tests for Flexible GraphRAG.

These tests call the live REST API only (not MCP).

Quick start:
    # One command: merge profile, start backend, pytest, stop backend (from repo root)
    uv run tests/integration/run_profile.py --profile neo4j-llamaindex

    # Or: start API yourself (cd flexible-graphrag && uv run start.py), then pytest tests/integration/

    # CI: all profiles
    uv run tests/integration/run_all_profiles.py

See tests/integration/README.md for full documentation.
"""
