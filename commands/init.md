# /init — Universal Project Bootstrap & Health Check

Initialize or verify any project environment. Auto-detects first-run vs health-check mode.

## Instructions

You are a project bootstrapper. Execute all steps below systematically, collecting results into the structured output table at the end. **This command is read-only in health-check mode — never create files, install packages, or make network calls.**

---

### Step 1: Detect Mode

Check for CLAUDE.md and MEMORY.md in the working directory (or project memory path):
- **Both exist** → **Health-check mode**: read-only, fast, no scaffolding. Skip file creation suggestions.
- **Either missing** → **First-run mode**: identify the project, suggest creating missing files. Do NOT create them automatically.

Report the detected mode.

---

### Step 2: Multi-Type Detection

Scan ALL project markers. Do NOT short-circuit on the first match — collect every type into an array.

| Marker | Type |
|--------|------|
| `requirements.txt`, `pyproject.toml`, `setup.py`, `Pipfile` | `python` |
| `package.json` | `node` |
| `Cargo.toml` | `rust` |
| `*.sln`, `*.csproj` | `dotnet` |
| `go.mod` | `go` |
| `*.xlsx`, `*.xls` + any `.py` importing `openpyxl` | `excel-openpyxl` |
| `docker-compose.yml`, `Dockerfile` | `docker` |
| `.env` file present | `env-config` |

**CLAUDE.md override**: If CLAUDE.md explicitly declares a project type or tech stack, include those types even if markers are missing.

Report all detected types as a comma-separated list.

---

### Step 3: Check Environment

Based on detected types:

**Python projects:**
- Run `python --version` — report version
- Check if a virtual environment is active (`VIRTUAL_ENV` env var or `sys.prefix != sys.base_prefix`)
- If venv detected, report its path; if not, report as warning

**Node projects:**
- Run `node --version` — report version
- Check if `node_modules/` exists

**All projects:**
- Report the working directory path
- Report OS/platform

---

### Step 4: Check Dependencies

**Python**: Run `pip list --format=json` (or `pip list`) and check for key packages:
- Read `requirements.txt` or `pyproject.toml` for expected packages
- If CLAUDE.md mentions specific packages (e.g., openpyxl, requests, flask), check those too
- Report each package: installed version or MISSING

**Node**: Check `node_modules/.package-lock.json` or run `npm ls --depth=0`

Only **report** missing packages — never install automatically.

---

### Step 5: Verify Configuration

- Check for `.env` file — report exists/missing (never print values)
- Check for token files referenced in CLAUDE.md (e.g., `raken_tokens.json`)
  - If found: check file is non-empty
  - If JWT format (3 dot-separated base64 segments): decode the middle segment, check `exp` field
  - If expired: warn with the exact expiry date
  - **Never make API calls** to validate tokens
- Check for config directories mentioned in CLAUDE.md or MEMORY.md
- Report each config item: present/missing/expired

---

### Step 6: Validate Data Files

Check key data files referenced by the project:

**Excel files (`.xlsx`):**
- **Lock detection**: Try `open(path, "r+b")` — if `PermissionError`, report as LOCKED with message "Close Excel first"
- If not locked: open with `openpyxl.load_workbook(path, read_only=True, data_only=True)`
- List sheet names found
- If CLAUDE.md or MEMORY.md documents expected sheets, validate they match
- Report row counts per sheet (approximate — count non-empty rows in column A)
- If MEMORY.md documents row counts/ranges, compare and warn if significantly different
- **Always close the workbook after reading**

**Database files (`.db`, `.sqlite`):**
- Check file exists and is readable
- Report file size and last modified date

**JSON/config data files:**
- Check referenced files exist
- Report file size and last modified date

Use `pathlib.Path` for all path operations (Windows compatibility).

---

### Step 7: Check MEMORY.md Status

If MEMORY.md exists:
- Report its last modified date
- Count the number of sections (## headings)
- Check for staleness indicators:
  - If it mentions dates, compare the most recent date to today
  - If it mentions row ranges, note they may be stale
  - If >30 days since last documented date, warn as potentially stale
- List any "Key Files" section entries and verify those files still exist

---

### Step 8: Check Scheduled Tasks & Automation

**Windows**: Run `schtasks /query /fo LIST /v` wrapped in try/except:
- Look for tasks related to the project name or directory
- Report task name, status, next run time
- If no tasks found, report as "None detected"
- Handle `PermissionError` gracefully — report as "Unable to query (permissions)"

**CLAUDE.md commands**: If CLAUDE.md has a `## Commands` section, list the available commands.

---

### Step 9: Project-Specific Intelligence

Read CLAUDE.md and MEMORY.md for known gotchas and surface relevant warnings:
- If MEMORY.md mentions specific gotchas (e.g., "Row Ranges Get Stale"), extract and display the warning
- If MEMORY.md has a "last updated" date for data, compare to today and warn if stale
- Check for any "MANDATORY" rules in MEMORY.md and list them briefly

---

### Step 10: Structured Output

Print the final report in this exact format:

```
══════════════════════════════════════════
 /init  <Project Name>  <YYYY-MM-DD>
══════════════════════════════════════════
 MODE     first-run | health-check
 TYPE     <comma-separated detected types>
 ENV      <status> <Python/Node version, venv status>
 DEPS     <status> <summary or list of missing>
 CONFIG   <status> <.env, tokens, API keys>
 DATA     <status> <workbooks, databases>
 SHEETS   <status> <sheet names match/mismatch>
 MEMORY   <status> <MEMORY.md freshness>
 TASKS    <status> <scheduled tasks, automation>
══════════════════════════════════════════
 STATUS   READY | N issues found
══════════════════════════════════════════
Status indicators:
  + = good / present / healthy
  ~ = warning / potentially stale / minor issue
  ! = error / missing / broken
```

Below the table, list:
1. Any action items (missing deps, locked files, expired tokens, stale data)
2. Available commands from CLAUDE.md (if any)
3. Key gotchas from MEMORY.md (if any)

---

## Idempotency Rules

- **Health-check mode is read-only**: no file creation, no installs, no network calls, no mutations
- **First-run mode**: only suggest actions — never execute them automatically
- Running this command twice must produce identical output (assuming no external changes)
- All output goes to stdout only — no side effects

## Windows Compatibility

- Use pathlib.Path for all path operations
- Wrap schtasks in try/except
- Handle PermissionError with "Close Excel first" message
- Use open(path, "r+b") for lock detection (not OS-specific file locking APIs)
