# Implementation Plan: Fix startup freeze

**Branch**: `001-fix-startup-freeze` | **Date**: 2026-11-19 | **Spec**: specs/001-fix-startup-freeze/spec.md

**Input**: Feature specification from `specs/001-fix-startup-freeze/spec.md`

**Note**: Retroactive plan — the code fix was already implemented before this Spec Kit run (per user request to run Spec Kit as a deep-verification pass). This plan documents the actual root cause, the actual change, and the verification approach, rather than proposing new design.

## Summary

App "Muse Landscape Studio" (FrameWeaver-Windows desktop host) freezes on every launch. Root cause: the pywebview `js_api` object passed to `webview.create_window()` held a public reference back to the pywebview `Window` object itself (`UpdateApi.window`). pywebview's own JS-API auto-exposure (`webview/util.py:get_functions`) walks every non-callable, non-underscore-prefixed attribute of the `js_api` object recursively via `dir()`/`getattr()`. Through `update_api.window` it reached `window.native` (the raw WinForms/WebView2 control), then `.AccessibilityObject.Bounds`, a property backed by `System.Drawing.Rectangle.Empty` — a static property that returns a *new* struct instance on every access, so pywebview's `id()`-based cycle guard never recognizes it as already-visited, producing unbounded recursion on a background thread on every window load. Fix: rename the attribute to `_window` (leading underscore), which `get_functions` explicitly skips, cutting off the reflection path with no change to pywebview itself.

## Technical Context

**Language/Version**: Python 3.12 (desktop host/backend), TypeScript/React (dashboard frontend, untouched by this fix)

**Primary Dependencies**: pywebview 6.2.1 (edgechromium/WebView2 GUI backend), FastAPI + uvicorn (local backend server on 127.0.0.1:8100), PyInstaller 6.22.3 (packaging)

**Storage**: N/A for this fix (no data model change)

**Testing**: Manual root-cause verification via real app logs (`Data/app.log`, `Data/desktop.log`); automated check via the app's own built-in `--ui-smoke-test` launch flag (waits for the dashboard to render, writes `ui-result.json`, exits) — run against both the raw Python entrypoint and the PyInstaller-frozen `.exe`

**Target Platform**: Windows 10/11 desktop (x64), WebView2 Runtime required

**Project Type**: Desktop app (Python backend + bundled React dashboard, packaged as a single-user Windows executable via PyInstaller + Inno Setup)

**Performance Goals**: Window must finish rendering within the existing 15s startup watchdog (`windows/launcher.py`); no new performance targets introduced

**Constraints**: Fix must not change pywebview (third-party, vendored in `.venv-build`) or require a pywebview upgrade; must not change the dashboard/React code; must be a minimal, surgical change confined to `windows/launcher.py`

**Scale/Scope**: Single file changed (`windows/launcher.py`), 2 lines (attribute rename + its one assignment site); no API/schema changes

## Constitution Check

*No project constitution has been authored yet (`.specify/memory/constitution.md` is still the unfilled template) — `/speckit-constitution` was not run, as it is out of scope for a single bug-fix verification pass. No gates to check; treated as pass by default.*

## Project Structure

### Documentation (this feature)

```text
specs/001-fix-startup-freeze/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (N/A — no data entities; file notes this and is skipped at content level)
├── quickstart.md        # Phase 1 output — reproduction + verification steps
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
D:\Code\FrameWeaver-Windows\
├── windows\
│   └── launcher.py       # <-- the only file changed: UpdateApi.window -> UpdateApi._window
├── agent\                # FastAPI backend (muse2api, muse_app, etc.) — unaffected
├── dashboard\             # React frontend, built via vite — unaffected
└── dist\MuseLandscapeStudio\   # PyInstaller onedir output, rebuilt from the fixed launcher.py
```

**Structure Decision**: Single-project desktop app structure (no frontend/backend split needed for this fix — the change is confined to the Windows desktop host layer, `windows/launcher.py`, which wraps the already-existing FastAPI backend and React dashboard).

## Complexity Tracking

*No constitution violations — not applicable.*
