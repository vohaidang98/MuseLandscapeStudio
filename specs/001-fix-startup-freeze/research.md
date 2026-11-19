# Phase 0 Research: Fix startup freeze

## Unknown: what exactly loops inside pywebview on window load?

- **Decision**: It is `webview/util.py:inject_pywebview -> get_functions(window._js_api)`, a reflection walk pywebview runs on a background thread every time a page load event fires, to auto-generate the JS-side `window.pywebview.api` object.
- **Rationale**: Confirmed by reading the vendored library source (`.venv-build/Lib/site-packages/webview/util.py` lines 180-211) and cross-referencing with `windows/launcher.py`: `window._js_api` is literally the `UpdateApi` instance passed as `js_api=update_api`, and `update_api.window = window` (set right after `create_window`, before `webview.start()`) gives the walk a path straight back into the live `Window` object.
- **Alternatives considered**: Initially suspected AnyDesk/UltraViewer (both running on the machine) triggering the freeze via Windows UI Automation probing the WebView2 control from outside the process. Ruled out by reproducing the exact same log spam with a plain `python windows/launcher.py --ui-smoke-test` run, in a clean scratch `FRAMEWEAVER_DATA_DIR`, with no remote-desktop interaction involved — the recursion is fully internal to the process and independent of any external AT/remote-control client.

## Unknown: why does the recursion never terminate?

- **Decision**: `get_functions` guards against cycles with `exposed_objects.append(id(obj))`, skipping an object it has already seen by `id()`. `AccessibilityObject.Bounds` resolves (via pythonnet/COM interop) to `System.Drawing.Rectangle.Empty`, a *static* property. Each access boxes a *new* `Rectangle` struct instance with its own `id()`, so the cycle guard never fires, and `Empty.Empty.Empty...` keeps expanding.
- **Rationale**: Directly observed in the real logs: the error string literally reads `window.native.AccessibilityObject.Bounds.Empty.Empty.Empty...` repeated to thousands of segments, matching exactly what unbounded path-concatenation under a failing `id()`-dedup would produce.
- **Alternatives considered**: Considered that the freeze was simply "this COM call throws, and WinForms logs a lot of exceptions" (a bounded, if noisy, failure) — rejected once the segment count and file growth (2.5MB app.log for one run) made clear this was unbounded, not just verbose.

## Unknown: correct fix without touching the vendored pywebview library

- **Decision**: Rename `UpdateApi.window` to `UpdateApi._window` (and its one assignment site). `get_functions` explicitly does `if name.startswith('_'): continue`, so this is the library's own documented escape hatch for "do not expose/walk this attribute."
- **Rationale**: Minimal, surgical, zero risk to pywebview's own behavior or to any other code path; matches the project's existing constraint of not vendoring/patching third-party packages.
- **Alternatives considered**:
  - Monkey-patching `webview.util.get_functions` at runtime to special-case `AccessibilityObject` — rejected as more invasive and fragile across pywebview version bumps.
  - Calling `UiaDisableProviderForHwnd` (Win32) to opt the window out of UI Automation entirely — rejected as unnecessary once the root cause was shown to be internal reflection, not external UIA probing; would not have fixed the actual bug.
  - Not storing a reference to `window` on `update_api` at all, and instead closing over `window` in a local closure for `check_update` — functionally equivalent but a larger diff than necessary; the leading-underscore rename is simpler and self-documenting.

## Unknown: how to verify the fix without manually watching the GUI

- **Decision**: Use the app's own existing `--ui-smoke-test` CLI flag (`windows/launcher.py`, `UI_SMOKE` branch): it creates the window hidden, waits for `window.events.loaded`, polls `document.getElementById("root")` via `evaluate_js` until React has rendered, writes `Data/ui-result.json`, then destroys the window and exits 0. Compare `app.log` size and absence of `AccessibilityObject` strings before/after.
- **Rationale**: This is a real, already-existing automated check built into the production code (not a new test harness), so it exercises the exact same `webview.create_window(..., js_api=update_api)` path end users hit.
- **Alternatives considered**: Writing a brand-new minimal pywebview repro script outside the app — rejected as extra, unnecessary surface when the app already ships a fit-for-purpose smoke-test flag.

## Build-environment pitfall discovered during verification (not part of the root cause, but blocked verification once)

- **Decision**: PyInstaller builds for this project MUST be run from a native PowerShell process, not Git Bash/MSYS.
- **Rationale**: A first build attempt run through the Bash tool (Git Bash) reported "Build complete!" with no errors, but produced a `.exe` with a corrupted PE header (did not start with `4D 5A`) and a corrupted bundled data file (`_internal/agent/models.json` contained LICENSE text instead of JSON) in the cached `build/` work directory. Deleting `build/`, `dist/MuseLandscapeStudio`, and `windows/pyinstaller-cache`, then rebuilding the identical command through PowerShell, produced a correct `.exe` (valid `4D 5A` header) and correct `models.json` on the first try.
- **Alternatives considered**: None needed — root cause of the corruption wasn't pursued further since the project's own `windows/build.ps1` already mandates PowerShell; the Bash-tool attempt was this session's own process error, not a project issue.
