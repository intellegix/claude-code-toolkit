# /gba-test — Universal GBA Integration Test Runner

$ARGUMENTS: test mode — game profile defines available modes (e.g., `smoke`, `gameplay`, `save`, `stress`, `full`, `ai`, `battle`, `nav`, `custom <description>`)

## 5 ABSOLUTE RULES (NEVER VIOLATE)
1. **VERIFY** state before every action (screenshot + frame check)
2. Use **ONLY** named RECIPES from the game's guide — never invent button sequences
3. Frame advances >30 require a **state check** before next action
4. **Screenshot** every 5 tool calls
5. If assertion fails → **STOP**, report failure + actual state, never retry blindly

## Step 1: Detect Game

1. `gba_get_frame` — if fails, stop and report "emulator not connected"
2. Read ROM title: `gba_read_memory(0x080000A0, 12)` — decode as ASCII
3. Match title against known profiles:

| ROM Title Contains | Profile |
|--------------------|---------|
| `POKEMON EMER` or `POKEMON FIRE` | `profiles/pokemon-embergold.md` |
| `BRAINATTIC` | `profiles/brain-attic.md` |

4. If no match: run **Generic Boot Test** only (see below), then stop

## Step 2: Load Profile

1. Read the matched profile file from `~/.claude/commands/profiles/`
2. Read the game's guide file (path specified in profile) **completely** — MANDATORY before any further MCP calls
3. Note the profile's available test modes and recipes

## Step 2.5: Johto Mode Prerequisites

If the requested mode starts with `johto-`:
1. Check which save state slots exist by attempting `gba_load_state(N)` for slots 2-8:
   - If slot loads without error and `pokemon_get_map` returns group=43 → slot is valid Johto checkpoint
   - Track which slots are available vs missing
2. Report available vs required slots
3. If **zero** Johto save states exist (none of slots 2-8 are valid), STOP and report:
   ```
   Johto test modes require save states at story checkpoints.
   Play through the game and save at each checkpoint per the guide (section 9).
   Required slots: 2 (New Bark) through 8 (Blackthorn City).
   ```
4. If **some** slots exist, proceed with available checkpoints only. Report which phases will be skipped due to missing slots.
5. Reload a known-good state before continuing: `gba_load_state(1)` to restore Kanto baseline.

## Step 3: Execute Test Mode

1. Map the user's requested mode to the profile's mode definitions
2. If the mode doesn't exist in the profile, report available modes and ask for clarification
3. Execute the mode's test sequence using ONLY the recipes and tools defined in the profile
4. For Pokemon profiles: game-specific MCP tools (e.g., `pokemon_get_party`) are available
5. For Brain Attic: all state reads use `gba_read_memory` against the memory map

## Step 4: Report Results

Use the profile's report format. Always include:
- Pass/fail table with expected vs actual values
- Total tool calls used
- Any FAIL → stop immediately and report, don't continue to next test

## Generic Boot Test (No Profile Match)

If the ROM title doesn't match any profile, run this minimal test:
1. `gba_get_frame` — ASSERT frame > 0
2. `gba_advance_frames(60)` — let game initialize
3. `gba_screenshot` — capture and describe what's visible
4. Report: ROM title, frame count, screenshot description

```
| # | Test | Expected | Actual | Result |
|---|------|----------|--------|--------|
| 1 | Emulator responds | frame > 0 | ... | PASS/FAIL |
| 2 | Advance 60 frames | no crash | ... | PASS/FAIL |
| 3 | Screenshot | visible content | ... | PASS/FAIL |
```

## Adding New Game Profiles

Create `~/.claude/commands/profiles/<game-name>.md` with:
- ROM title pattern for detection
- Guide file path
- Memory map (if using `gba_read_memory`)
- Game-specific MCP tools (if any)
- Test modes with named recipes
- Report format template
