# flake8: noqa
"""
Backend package for the minimal LLM web UI.

Modules:
    settings: Configuration loading and persistence helpers.
    storage:  Append-only JSONL data stores for conversations and indices.
    llm:      Llama.cpp client wrapper and tool registry utilities.
    tasks:    Background worker process, task queue management, and idle monitor.
    templates:HTML rendering helpers for the mostly static interface.
    main:     FastAPI application wiring everything together.
"""
