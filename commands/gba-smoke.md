# /gba-smoke — Universal GBA Emulator Smoke Test

## 5 ABSOLUTE RULES
1. VERIFY state before every action (screenshot + frame check)
2. ONLY named RECIPES — never invent button sequences
3. Frame advances >30 → state check first
4. Screenshot every 5 tool calls
5. Assertion fail → STOP, report, never retry blindly

## Tier 1: Universal Assertions (4 tests, any ROM)

These run BEFORE game detection. If any fail, stop immediately.

1. `gba_get_frame` → ASSERT responds with frame number > 0 (emulator running)
2. `gba_screenshot` → ASSERT visible content on screen (not black/blank)
3. `gba_advance_frames(60)` → ASSERT no error (ROM executes without crash)
4. `gba_get_frame` → ASSERT frame number increased (game loop is advancing)

## Tier 2: Game-Specific Assertions

### Step 1: Detect Game
Read ROM title: `gba_read_memory(0x080000A0, 12)` — decode as ASCII.

| ROM Title Contains | Profile | Action |
|--------------------|---------|--------|
| `POKEMON EMER` or `POKEMON FIRE` | `profiles/pokemon-embergold.md` | Load profile, run its `smoke` mode |
| `BRAINATTIC` | `profiles/brain-attic.md` | Load profile, run its `smoke` mode |
| (no match) | none | Skip Tier 2, report Tier 1 only |

### Step 2: Load Profile and Guide
1. Read the matched profile from `~/.claude/commands/profiles/`
2. Read the game's guide file **completely** (path in profile) — MANDATORY
3. Execute the profile's `smoke` mode test sequence

### Step 3: Merge Reports
Combine Tier 1 + Tier 2 results into a single table.

## Report Format

### With Game Profile
```
| # | Tier | Test | Expected | Actual | Result |
|---|------|------|----------|--------|--------|
| 1 | T1 | Emulator responds | frame > 0 | ... | PASS/FAIL |
| 2 | T1 | Screenshot | visible screen | ... | PASS/FAIL |
| 3 | T1 | Frame advance | no error | ... | PASS/FAIL |
| 4 | T1 | Frame advancing | frame increased | ... | PASS/FAIL |
| 5+ | T2 | (game-specific) | ... | ... | PASS/FAIL |
```

### Without Game Profile
```
| # | Tier | Test | Expected | Actual | Result |
|---|------|------|----------|--------|--------|
| 1 | T1 | Emulator responds | frame > 0 | ... | PASS/FAIL |
| 2 | T1 | Screenshot | visible screen | ... | PASS/FAIL |
| 3 | T1 | Frame advance | no error | ... | PASS/FAIL |
| 4 | T1 | Frame advancing | frame increased | ... | PASS/FAIL |
```
ROM title: `<detected title>` — no matching profile found. Only universal tests ran.

Total tool calls at end. Any FAIL → stop and report.
