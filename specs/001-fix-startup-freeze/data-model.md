# Phase 1 Data Model: Fix startup freeze

N/A — this fix changes no persisted data, no database schema, and no request/response shape. It renames one
in-memory Python attribute (`UpdateApi.window` → `UpdateApi._window`) used only within a single process's
lifetime to hold a reference to the current pywebview window object. No entities to document.
