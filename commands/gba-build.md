# /gba-build — Universal GBA Game Builder

## Usage
```
/gba-build [subcommand] [args]
```

## Subcommands

### `new <name>` — Scaffold a new GBA project
Creates a complete project skeleton ready to compile. After scaffolding, runs `/research-perplexity` to plan the module breakdown for the game.

### `develop <description>` — Research-driven modular game build
The main game development workflow. Takes a game description and builds the entire game modularly with research gates and E2E testing at every step.

### `build` — Compile the current project
Runs make/cmake, captures errors, loads ROM into mGBA, and takes a screenshot.

### `test` — Run the game's test suite
Executes ALL module tests in sequence via MCP tools. Reports per-module pass/fail.

### `docs` — Generate gameplay documentation
Auto-generates GAMEPLAY.md, TECHNICAL.md, and MCP-TOOLS.md from code.

### `asset <file>` — Convert a graphics/audio file
Runs grit or mmutil with appropriate flags.

---

## Instructions

### Step 1: Load the GBA Builder Skill
Read the gba-builder skill for complete GBA development reference. This gives you:
- Hardware register map (hardware-ref.md)
- Game architecture patterns (architecture-patterns.md)
- Asset pipeline reference (asset-pipeline.md)
- Testing framework (testing-framework.md)
- Documentation generator (docs-generator.md)

### Step 2: Detect Context

Determine what's being requested from the subcommand:

---

**If `develop <description>`:**

This is the primary game-building workflow. It enforces research-driven decisions, modular construction, and E2E testing gates.

#### Phase A: Research
Run `/research-perplexity` with the game description to get:
- Recommended architecture (which patterns from architecture-patterns.md apply)
- Module breakdown (what to build and in what order)
- Asset requirements (sprites, tilesets, audio needed)
- GBA-specific constraints and gotchas for this genre
- Estimated VRAM/RAM budget

Include the game description and relevant context from architecture-patterns.md and hardware-ref.md in the research query.

#### Phase B: Plan
From the research results, create a modular build plan. Each module should be a self-contained system that can be compiled, tested, and verified independently. Example breakdown:

```
Module 1: Display Setup (Mode 0, BG layers, palette loading)
Module 2: Player Sprite (load, render, basic animation)
Module 3: Input Handling (d-pad movement, button actions)
Module 4: Tile Map (load level, scrolling camera)
Module 5: Collision (tile-based, player vs walls/objects)
Module 6: Entities (enemy pool, spawn/despawn lifecycle)
Module 7: Combat (attack, damage, HP, death)
Module 8: UI (HUD, score display, health bar)
Module 9: Audio (BGM + SFX via maxmod)
Module 10: Save System (SRAM byte-write pattern)
Module 11: Game Flow (title screen, game over, level transitions)
Module 12: Polish (screen transitions, juice effects, balance tuning)
```

Create a TodoWrite task list for each module in the plan.

#### Phase C: Build Loop
For EACH module in sequence:

1. **Research Gate** — If the module involves a non-trivial decision, run `/research-perplexity` first:
   - Game architecture selection (before Module 1)
   - Sprite/tileset design decisions (before sprite/tilemap modules)
   - Combat or scoring formula design (before combat modules)
   - Save data structure design (before save module)
   - Any time you are unsure about a GBA hardware constraint

2. **Code** — Write the code for THIS module only. Keep it focused.

3. **Build** — Run `/gba-build build` to compile. Fix any errors before proceeding.

4. **E2E Test** — Run the module-specific E2E test protocol:
   - `gba_build` → compile succeeds
   - `gba_flash_rom` → ROM loads in mGBA
   - `gba_screenshot` → visual output correct
   - `gba_read_io("REG_DISPCNT")` → display mode correct
   - `gba_read_oam` → sprites positioned correctly (if applicable)
   - `gba_read_memory` → game state values correct
   - `gba_profile_frame` → within VBlank budget (< 280,896 cycles)
   - Module-specific assertions (varies per module)

5. **Document** — Run `/gba-build docs` to update documentation.

6. **Gate** — ONLY proceed to the next module if ALL tests pass. If tests fail:
   - Debug the issue
   - Fix the code
   - Re-build and re-test
   - NEVER skip a failing test

7. **Checkpoint** — After each passing module, note the current state. This is the new baseline.

#### Phase D: Integration
After all modules pass individually:
1. Run the full test suite: `/gba-build test`
2. Run `/gba-build docs` for final documentation
3. Take a final screenshot and profile
4. Summarize what was built, module-by-module

---

**If `new <name>`:**
1. Ask the user which engine to use (present options):
   - **Butano** (C++17, recommended) — batteries included, handles sprites/BGs/audio/saves
   - **libtonc** (C) — thin wrapper over hardware, more control
   - **bare metal** — devkitARM only, direct register access
2. Create project directory structure:
   ```
   <name>/
   ├── src/
   │   └── main.cpp (or main.c)
   ├── include/
   ├── graphics/
   ├── audio/
   ├── data/
   ├── build/
   ├── docs/
   ├── tests/
   ├── CMakeLists.txt (or Makefile)
   ├── .gitignore
   └── CLAUDE.md
   ```
3. Copy the appropriate template from `~/.claude/skills/gba-builder/templates/`
4. Replace all `{{PROJECT_NAME}}` placeholders with the actual project name
5. Create a project-specific CLAUDE.md with:
   - Build instructions
   - Project structure description
   - Engine-specific notes
   - Link to GBA Builder skill for reference
6. Create `.gitignore` with: `build/`, `*.gba`, `*.elf`, `*.sav`
7. Report what was created
8. **Post-scaffold research:** Run `/research-perplexity` to plan the module breakdown for this project based on its name and any context provided

---

**If `build`:**
1. Detect project type from build files:
   - `CMakeLists.txt` → Butano (cmake)
   - `Makefile` → libtonc/bare (make)
2. Run the appropriate build command:
   - Butano: `cmake -S . -B build && cmake --build build`
   - libtonc/bare: `make`
3. If build fails, analyze errors and suggest fixes
4. If build succeeds:
   - Report ROM file size and memory usage
   - If mGBA MCP is available, auto-flash ROM with `gba_flash_rom`
   - Take a `gba_screenshot` to verify visual output
5. Report success/failure with structured output

---

**If `test`:**
1. Check for `tests/` directory
2. If `test_config.json` exists, load memory addresses
3. Run ALL module tests in sequence:
   - If Lua tests exist: use `gba_run_lua_test` for each
   - If Node.js tests exist: run with vitest
   - If no formal tests exist, run the standard E2E protocol:
     a. `gba_flash_rom` → verify ROM loads
     b. `gba_screenshot` → verify visual output
     c. `gba_read_io("REG_DISPCNT")` → verify display mode
     d. `gba_read_oam` → verify sprite state
     e. `gba_profile_frame` → verify within VBlank budget
     f. `gba_check_vblank_budget` → confirm frame timing
4. Report results per module in standard format:
   ```
   ═══════════════════════════════════════
     GBA Test Report: <project>
   ═══════════════════════════════════════
   Module 1: Display Setup
     ✓ Display mode is Mode 0
     ✓ BG0 enabled
     ✓ OBJ layer enabled
   Module 2: Player Sprite
     ✓ OAM slot 0 visible
     ✓ Sprite at expected position
     ✗ Animation frame incorrect — expected 2, got 0
   ───────────────────────────────────────
   Results: N PASS | N FAIL | N SKIP
   Performance: Xk cycles/frame (Y% budget)
   ───────────────────────────────────────
   ```

---

**If `docs`:**
1. Read all source files in `src/`
2. Identify game entities, mechanics, controls, memory layout
3. Generate/update:
   - `docs/GAMEPLAY.md` — Game mechanics and controls
   - `docs/TECHNICAL.md` — Memory layout and performance
   - `docs/MCP-TOOLS.md` — Memory addresses for testing
4. Use the docs-generator.md reference for format
5. Verify memory addresses against `.map` file if available

---

**If `asset <file>`:**
1. Detect file type from extension:
   - `.png`, `.bmp` → graphics (use grit)
   - `.xm`, `.mod`, `.s3m`, `.it` → music (use mmutil)
   - `.wav` → sound effect (use mmutil)
2. Detect project type for output format:
   - Butano: create matching `.json` config, place in `graphics/` or `audio/`
   - libtonc: run grit/mmutil directly, output to `build/`
3. For graphics, auto-detect appropriate flags:
   - Small image (≤64px) → sprite (`-Mw -Mh`)
   - Large image (>64px, power of 2) → tileset (`-mRtf`)
   - 240x160 exact → bitmap mode (`-gb`)
4. Report conversion results and generated files

### Step 3: Execute and Report
- Always report what was done in structured format
- On errors, provide specific fix suggestions
- Screenshot the running ROM when possible (via MCP)
- After completing all work, suggest running `/research-perplexity` for strategic next steps

## Research Gates Reference

These decision points MUST use `/research-perplexity` before proceeding:

| Decision Point | When | What to Research |
|---------------|------|-----------------|
| Architecture Selection | Before Module 1 | Best GBA patterns for this genre, mode selection, VRAM layout |
| Sprite Design | Before sprite modules | Sprite sizes, animation frames, palette strategy |
| Tilemap Design | Before tilemap modules | Tile size, map dimensions, scrolling approach, compression |
| Combat Formula | Before combat modules | Damage calculation, hitbox design, frame timing |
| Save Structure | Before save module | Save data layout, checksum strategy, SRAM byte-write pattern |
| Audio Strategy | Before audio modules | Channel allocation, mixing rate, maxmod vs direct sound |
| Hardware Uncertainty | Any time | When unsure about a GBA hardware constraint or register behavior |

## E2E Test Protocol (Per Module)

After each module is built, run these checks:

```
1. gba_build           → compile succeeds (zero errors)
2. gba_flash_rom       → ROM loads in mGBA without crash
3. gba_screenshot      → visual output matches expectations
4. gba_read_io         → REG_DISPCNT and relevant IO correct
5. gba_read_oam        → sprites positioned correctly (if applicable)
6. gba_read_memory     → game state values match expected
7. gba_profile_frame   → cycles < 280,896 (VBlank budget)
8. [module-specific]   → custom assertions per module
```

## Prerequisites
- **devkitPro** installed: `pacman -S gba-dev`
- **Butano** (if using): clone from https://github.com/GValiente/butano, set `BUTANO_PATH`
- **mGBA** running with Lua MCP server for testing/flashing features
- MCP server registered globally (see `~/.claude/settings.json`)

## Examples

```bash
# Create a new Butano project
/gba-build new space-shooter

# Build a full game with research-driven modular workflow
/gba-build develop "a top-down dungeon crawler with 3 floors, enemies, and a boss"

# Build the current project
/gba-build build

# Run all module tests
/gba-build test

# Generate documentation
/gba-build docs

# Convert a sprite sheet
/gba-build asset graphics/player.png
```
