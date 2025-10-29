# Design Principles

## Architecture
- **Server-rendered first**: FastAPI templates own the canonical markup and styling so the UI works without client-side frameworks or heavy hydration.
- **Progressive enhancement**: JavaScript augments interactions (polling, mentions, optimistic updates) but core flows—including form submissions—remain functional with JS disabled.
- **File-backed state**: Conversations, tasks, and settings persist as JSON/JSONL under `data/`, ensuring deterministic state reloads and simplifying local inspection.

## User Experience
- **Always-visible context**: The dashboard keeps conversations, chat, and the priority queue on one screen to reduce navigation and maintain situational awareness.
- **Terse, legible cards**: Task cards compress to three text lines plus a single action, preserving readability while preventing scroll overflow in constrained lanes.
- **Predictable empty states**: Placeholders mirror the eventual layout (two completed slots, one queued slot) so layout does not shift as work arrives.

## Interaction Resilience
- **Interval polling with diffing**: The client polls `/state` every five seconds and only swaps DOM sections when the backend signature changes, avoiding redundant reflows.
- **Idle-aware feedback**: Worker, idle, and LLM badges reflect live status, giving operators immediate feedback about system health during hands-off periods.
- **Graceful degradation**: Mention helpers, reasoning toggles, and scroll anchoring all fall back cleanly if the enhancement script cannot run.

## Maintainability
- **Feature-oriented structure**: UI code resides under `src/features/*`, shared pieces live in `src/components`, and templates concentrate HTML+CSS in `app/templates.py`.
- **Consistent styling**: Inline token variables (palette, spacing, typography) centralize visual tweaks without requiring a global CSS pipeline.
- **Observable defaults**: Logging, signature hashes, and placeholder records expose system behavior, streamlining debugging without extra tooling.
