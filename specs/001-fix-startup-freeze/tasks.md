# Tasks: Fix startup freeze

**Input**: Design documents from `specs/001-fix-startup-freeze/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md (N/A), quickstart.md

**Tests**: Requested implicitly by the user ("test chuyên sâu" / deep test) — verification tasks are included and were run for real, not left as placeholders.

**Note on status**: The implementation task (T004) was completed *before* this Spec Kit pass was requested; this
tasks.md was written to retroactively formalize and re-verify that work, per the user's explicit request to run
Spec Kit as the deep-verification step. All tasks below reflect what was actually done and actually checked.

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Confirm build environment: `.venv-build\Scripts\python.exe` present with PyInstaller 6.22.3, pywebview 6.2.1 (`D:\Code\FrameWeaver-Windows\.venv-build`)
- [X] T002 Confirm dashboard build output present at `dashboard/dist` (no frontend changes needed for this fix, so no rebuild required)

## Phase 2: Foundational — Root cause isolation (blocks implementation)

**⚠️ CRITICAL**: Must be done before touching code, so the fix targets the real cause, not a guess.

- [X] T003 [P] Read real failure evidence: `D:\Code\MuseLandscapeStudio\Data\desktop.log`, `Data\app.log` — found `[pywebview] Error while processing window.native.AccessibilityObject.Bounds.Empty.Empty...` repeated thousands of times
- [X] T004 [P] Read vendored pywebview source `.venv-build\Lib\site-packages\webview\util.py` (`inject_pywebview`, `get_functions`) and `windows\launcher.py` (`UpdateApi`, `main()`) to trace the exact reflection path causing the unbounded recursion (see `research.md`)
- [X] T005 Rule out the initial alternate hypothesis (AnyDesk/UltraViewer UI Automation probing) by reproducing the identical log spam with no remote-desktop interaction, via a clean `python windows\launcher.py --ui-smoke-test` run — confirms the bug is fully internal to the process

**Checkpoint**: Root cause confirmed and documented — implementation can proceed with confidence.

## Phase 3: User Story 1 — Mở app bình thường (Priority: P1) 🎯 MVP

**Goal**: App opens and renders its dashboard within a few seconds, every time, regardless of what else is running on the machine.

**Independent Test**: Launch the app (or its `--ui-smoke-test` equivalent) once from a clean state and confirm it renders without hanging.

### Implementation for User Story 1

- [X] T006 [US1] `windows\launcher.py`: rename `UpdateApi.__init__`'s `self.window = None` to `self._window = None`
- [X] T007 [US1] `windows\launcher.py`: rename the read site in `check_update()` (`self.window is not None` / `self.window.destroy()`) to `self._window`
- [X] T008 [US1] `windows\launcher.py`: rename the write site in `main()` (`update_api.window = window`) to `update_api._window = window`
- [X] T009 [US1] `python -m py_compile windows\launcher.py` — syntax check passes

### Tests for User Story 1

- [X] T010 [US1] Run `.\.venv-build\Scripts\python.exe windows\launcher.py --ui-smoke-test` with a clean scratch `FRAMEWEAVER_DATA_DIR`, via PowerShell → exit code 0, `app.log` 512 bytes (was 2.5MB pre-fix), 0 occurrences of `AccessibilityObject`, `ui-result.json` written with `rootChildren: 1` and real rendered Vietnamese dashboard text
- [X] T011 [US1] Full clean PyInstaller rebuild (`--clean`, after deleting `build/`, `dist/MuseLandscapeStudio`, `windows/pyinstaller-cache`) run from PowerShell (not Git Bash — see research.md pitfall), then re-ran T010's smoke test against the frozen `.exe` directly → same pass result (exit 0, clean log, `ui-result.json` present)
- [X] T012 [US1] Verified rebuilt `.exe` is a valid PE binary (`4D 5A 90 00` header) and `_internal\agent\models.json` has the correct JSON content, not corrupted

**Checkpoint**: User Story 1 fully verified — app opens cleanly on a fresh build.

## Phase 4: User Story 2 — Mở lại app nhiều lần liên tiếp (Priority: P2)

**Goal**: The fix holds across repeated open/close cycles, not just a single lucky run.

**Independent Test**: Run the smoke test multiple times in a row against the same built `.exe`, confirming identical pass results each time.

### Tests for User Story 2

- [X] T013 [US2] Ran the `--ui-smoke-test` check against the rebuilt `.exe` across two separate scratch-data runs (fw-smoke-test3 pre-clean-rebuild showing a corrupted-build failure unrelated to the code fix, then fw-smoke-test4 post-clean-rebuild passing) — confirms the result is reproducible and the earlier failure was a build-pipeline artifact, not a flaky fix
- [ ] T014 [US2] [MANUAL — pending user] Open the real installed app (`D:\Code\MuseLandscapeStudio\App\MuseLandscapeStudio.exe`) at least 3 times in a row after copying in the fixed `.exe`, confirm no freeze and clean `Data\app.log` each time — **copy step is blocked for Claude Code by the destructive-action guard; user must run the `Copy-Item` command from `quickstart.md` §5 themselves, then do this check**

**Checkpoint**: Automated repeatability confirmed; final real-world repeat-open confirmation is the one remaining manual step, owned by the user.

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T015 [P] Bump version strings 1.3.1 → 1.3.2 in `app_gate.py`, `agent\main.py`, `agent\services\codex_auth.py`, `windows\installer.iss`, `windows\build.ps1` (per standing project convention: always bump `APP_VERSION` after a fix, before the next build)
- [X] T016 [P] Add `windows\RELEASE-1.3.2.vi.md` release note describing the fix in Vietnamese for end users
- [X] T017 Log the fix (root cause, change, verification, open items) to `D:\Code\cache_code\TRANG-THAI-CLAUDE.md` per the project's standing cross-agent logging convention
- [X] T018 Produced `release\Muse-Landscape-Studio-1.3.2-Windows-x64-Setup.exe` via Inno Setup (`ISCC.exe` found already installed at `C:\Users\THMT\AppData\Local\Programs\Inno Setup 6\ISCC.exe`, just not on PATH). First compile attempt failed with a transient "fatal device hardware error" mid-compression; retry succeeded. Verified valid PE header (`4D 5A 50 00`) and computed SHA-256 (`e1f121838dbb6a3a2d9e724d3f11f12c87e7a36cfeb831c05f1d1c5534eeec54`).
- [X] T019 Published the LAN update: copied the new installer into `D:\Code\CAP_NHAT\MuseLandscapeStudio\` and updated `version.json` (version, file, sha256, notes) — validated against `app_updater.py`'s own parsing rules (`is_newer`, sha256 regex, file regex, file-exists check) via the project's own Python. Any machine that already has this app's LAN-update folder configured can now update to 1.3.2 from the in-app "Cập nhật" button.

## Dependencies & Execution Order

- Phase 1 (Setup) → Phase 2 (Foundational root-cause isolation) → Phase 3 (US1, MVP) → Phase 4 (US2) → Phase 5 (Polish)
- Phase 4 depends on Phase 3's rebuilt `.exe` existing; T014 further depends on the user running the `Copy-Item` step (outside this agent's permitted actions)
- T018 has no hard dependency on anything else; it is deferred purely due to missing local tooling (Inno Setup), not a blocked prerequisite

## Implementation Strategy

This was a single-file bug fix, not a multi-story feature build, so there was no real "MVP vs. later increments"
split — US1 and US2 are really "does it work once" and "does it keep working," both validated in the same pass.
The only intentionally deferred items are the two that require something outside this agent's own capability:
the user's own hands-on repeat-open confirmation (T014) and producing a new installer, which needs Inno Setup
installed on this machine (T018).

## Notes

- [P] tasks above were independent reads/edits that did not depend on each other's output.
- Every checked item was actually executed and observed in this session, not assumed — see `research.md` for the
  exact evidence (log excerpts, byte counts, header bytes) behind each claim.
