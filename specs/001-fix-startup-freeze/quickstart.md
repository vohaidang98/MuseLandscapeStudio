# Quickstart: Verify the startup-freeze fix

## Prerequisites

- Repo checked out at `D:\Code\FrameWeaver-Windows`, build venv present at `.venv-build\Scripts\python.exe`
  (create with `windows/build.ps1` if missing — needs Python 3.12, `pip install -r windows/requirements-build.lock`).
- Dashboard already built at `dashboard/dist` (only needs rebuilding if frontend code changed — it did not for this fix).
- **Run every build/launch step from native PowerShell, never Git Bash** — see `research.md` for why (Git Bash
  silently corrupted the PyInstaller output once during this fix's own verification).

## 1. Reproduce the bug (optional, on the pre-fix code)

```powershell
$env:FRAMEWEAVER_DATA_DIR = "$env:TEMP\fw-repro"
Remove-Item -Recurse -Force $env:FRAMEWEAVER_DATA_DIR -ErrorAction SilentlyContinue
Set-Location D:\Code\FrameWeaver-Windows
.\.venv-build\Scripts\python.exe windows\launcher.py --ui-smoke-test
```

Expect: process hangs past 15s, or `Data/app.log` under `$env:FRAMEWEAVER_DATA_DIR` fills with thousands of
`[pywebview] Error while processing window.native.AccessibilityObject.Bounds.Empty.Empty...` lines.

## 2. Apply the fix

Already applied in `windows/launcher.py`:
- `UpdateApi.__init__`: `self.window = None` → `self._window = None`
- `UpdateApi.check_update`: `self.window.destroy()` → `self._window.destroy()`
- In `main()`: `update_api.window = window` → `update_api._window = window`

## 3. Rebuild

```powershell
Set-Location D:\Code\FrameWeaver-Windows
Remove-Item -Recurse -Force build, dist\MuseLandscapeStudio, windows\pyinstaller-cache -ErrorAction SilentlyContinue
$env:PYTHONPATH = "D:\Code\FrameWeaver-Windows"
$env:PYINSTALLER_CONFIG_DIR = "D:\Code\FrameWeaver-Windows\windows\pyinstaller-cache"
.\.venv-build\Scripts\python.exe -m PyInstaller --noconfirm --clean windows\FrameWeaver.spec
```

Verify the output is a real PE binary before trusting it:

```powershell
[System.IO.File]::ReadAllBytes("dist\MuseLandscapeStudio\MuseLandscapeStudio.exe")[0..3] |
  ForEach-Object { $_.ToString('X2') }
# must print: 4D 5A 90 00
```

## 4. Automated verification (the actual test)

```powershell
$env:FRAMEWEAVER_DATA_DIR = "$env:TEMP\fw-verify"
Remove-Item -Recurse -Force $env:FRAMEWEAVER_DATA_DIR -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $env:FRAMEWEAVER_DATA_DIR | Out-Null
Set-Location D:\Code\FrameWeaver-Windows\dist\MuseLandscapeStudio
$p = Start-Process -FilePath .\MuseLandscapeStudio.exe -ArgumentList "--ui-smoke-test" -PassThru
$exited = $p.WaitForExit(60000)
if (-not $exited) { Stop-Process -Id $p.Id -Force; "FAIL: timed out / still freezing" }
else { "exit code: $($p.ExitCode)" }
```

**Pass criteria** (maps to spec Success Criteria SC-001..SC-003):
- Exit code `0` within 60s (well under the app's own 15s startup watchdog + smoke-test margin).
- `Get-Content "$env:FRAMEWEAVER_DATA_DIR\app.log" | Select-String AccessibilityObject` → **no matches**.
- `(Get-Item "$env:FRAMEWEAVER_DATA_DIR\app.log").Length` → a few hundred bytes, not megabytes.
- `Test-Path "$env:FRAMEWEAVER_DATA_DIR\ui-result.json"` → `$true`, and its `rootChildren` field is `> 0`
  (the React dashboard actually rendered content, not an empty shell).

## 5. Deploy to the real install

The user's actual installed app lives at `D:\Code\MuseLandscapeStudio\App` (same path Inno Setup's
`DefaultDirName` points at). Copying just the rebuilt `.exe` over the installed one is enough — the PyInstaller
onedir `_internal\` folder (third-party DLLs, etc.) is unchanged by this fix:

```powershell
Copy-Item "D:\Code\FrameWeaver-Windows\dist\MuseLandscapeStudio\MuseLandscapeStudio.exe" `
  "D:\Code\MuseLandscapeStudio\App\MuseLandscapeStudio.exe" -Force
```

Close the app first if it is running. No new `.exe` installer was produced in this pass (Inno Setup 6 /
`ISCC.exe` is not installed on this machine) — this only updates the already-installed copy in place.
