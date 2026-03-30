# /nds-build — Universal NDS Game Builder

## Usage
```
/nds-build [subcommand] [args]
```

## Subcommands

### `new <name>` — Scaffold a new NDS project
Creates a complete project skeleton ready to compile. After scaffolding, runs `/research-perplexity` to plan the module breakdown for the game.

### `develop <description>` — Research-driven modular game build
The main game development workflow. Takes a game description and builds the entire game modularly with research gates and E2E testing at every step.

### `build` — Compile the current project
Runs make, packages with ndstool, loads ROM into DeSmuME, and takes a screenshot of both screens.

### `test` — Run the game's test suite
Executes ALL module tests in sequence via MCP tools. Reports per-module pass/fail.

### `docs` — Generate gameplay documentation
Auto-generates GAMEPLAY.md, TECHNICAL.md, and MCP-TOOLS.md from code.

### `asset <file>` — Convert a graphics/audio file
Runs grit (with NDS-specific flags) or mmutil with appropriate settings.

---

## Instructions

### Step 1: Load the NDS Builder Skill
Read the nds-builder skill for complete NDS development reference. This gives you:
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
- NDS-specific constraints and gotchas for this genre
- Estimated VRAM/RAM budget (main engine + sub engine)
- Dual-screen layout strategy (what goes on which screen)
- Touch screen interaction design (if applicable)

Include the game description and relevant context from architecture-patterns.md and hardware-ref.md in the research query.

#### Phase B: Plan
From the research results, create a modular build plan. Each module should be a self-contained system that can be compiled, tested, and verified independently. Example breakdown:

```
Module 1: Display Setup (Main+Sub engines, VRAM bank mapping)
Module 2: Player Sprite (main engine OAM, sprite loading)
Module 3: Input Handling (d-pad, buttons, touch screen)
Module 4: Tile Map (main engine BG, scrolling)
Module 5: Sub Screen UI (bottom screen HUD/map/info)
Module 6: Collision (tile-based or AABB)
Module 7: Entities (object pool, spawn/despawn)
Module 8: Combat/Mechanics (genre-specific)
Module 9: Audio (16-channel sound via ARM7)
Module 10: Save System (libfat SD save)
Module 11: Game Flow (title, game over, transitions)
Module 12: Polish (dual-screen transitions, touch feedback)
```

Create a TodoWrite task list for each module in the plan.

#### Phase C: Build Loop
For EACH module in sequence:

1. **Research Gate** — If the module involves a non-trivial decision, run `/research-perplexity` first:
   - Game architecture selection (before Module 1)
   - Dual-screen layout decisions (before Module 1 and Module 5)
   - Sprite/tileset design decisions (before sprite/tilemap modules)
   - Touch screen interaction design (before Module 3 and Module 5)
   - Combat or scoring formula design (before combat modules)
   - Save data structure design (before save module)
   - ARM7/ARM9 responsibility split (before audio module)
   - Any time you are unsure about an NDS hardware constraint

2. **Code** — Write the code for THIS module only. Keep it focused. Remember the ARM9/ARM7 split: game logic on ARM9, audio/wifi on ARM7.

3. **Build** — Run `/nds-build build` to compile. Fix any errors before proceeding.

4. **E2E Test** — Run the module-specific E2E test protocol:
   - `make` → compile succeeds (both ARM9 + ARM7)
   - `ndstool` → ROM packages correctly
   - `nds_load_rom` → ROM loads in DeSmuME
   - `nds_advance_frames` → game runs without crash
   - `nds_screenshot` → visual output on both screens correct
   - `nds_read_memory` → game state values correct
   - `nds_touch_screen` → touch input works (if applicable)
   - Module-specific assertions (varies per module)

5. **Document** — Run `/nds-build docs` to update documentation.

6. **Gate** — ONLY proceed to the next module if ALL tests pass. If tests fail:
   - Debug the issue
   - Fix the code
   - Re-build and re-test
   - NEVER skip a failing test

7. **Checkpoint** — After each passing module, note the current state. This is the new baseline.

#### Phase D: Integration
After all modules pass individually:
1. Run the full test suite: `/nds-build test`
2. Run `/nds-build docs` for final documentation
3. Take a final screenshot of both screens and verify
4. Summarize what was built, module-by-module

---

**If `new <name>`:**
1. Ask the user which library to use (present options):
   - **libnds** (C, recommended) — official devkitPro library, hardware access with convenience functions
   - **NightFox's Lib** (C) — higher-level wrapper over libnds for 2D games
   - **bare metal** — devkitARM only, direct register access
2. Create project directory structure:
   ```
   <name>/
   ├── arm9/
   │   └── source/
   │       └── main.c (or main.cpp)
   │   └── include/
   ├── arm7/
   │   └── source/
   │       └── main.c
   │   └── include/
   ├── graphics/
   ├── audio/
   ├── data/
   │   └── nitrofiles/      (NitroFS assets)
   ├── build/
   ├── docs/
   ├── tests/
   ├── Makefile              (top-level, delegates to arm9/ and arm7/)
   ├── arm9/Makefile
   ├── arm7/Makefile
   ├── .gitignore
   └── CLAUDE.md
   ```
3. Copy the appropriate template from `~/.claude/skills/nds-builder/templates/libnds/`
4. Replace all `{{PROJECT_NAME}}` placeholders with the actual project name
5. Create a project-specific CLAUDE.md with:
   - Build instructions (make → ndstool → .nds output)
   - Project structure description (ARM9 + ARM7 subdirs)
   - Library-specific notes
   - VRAM bank allocation plan
   - Link to NDS Builder skill for reference
6. Create `.gitignore` with: `build/`, `*.nds`, `*.elf`, `*.arm9`, `*.arm7`, `*.sav`
7. Report what was created
8. **Post-scaffold research:** Run `/research-perplexity` to plan the module breakdown for this project based on its name and any context provided

---

**If `build`:**
1. Detect project type from build files:
   - `Makefile` with arm9/arm7 subdirs → standard libnds project
   - Single `Makefile` → simplified project (arm9 only, default arm7)
2. Run the build:
   - `make` → compiles ARM9 + ARM7 binaries
   - `ndstool -c <name>.nds -9 arm9/<name>.arm9 -7 arm7/<name>.arm7 -b icon.bmp "Title;Subtitle;Author"` → packages .nds ROM
   - If NitroFS files exist in `data/nitrofiles/`: add `-d data/nitrofiles` to ndstool
3. If build fails, analyze errors and suggest fixes. Common issues:
   - ARM9/ARM7 linker conflicts
   - VRAM bank mapping collisions
   - Missing libnds headers (check `nds.h` include)
4. If build succeeds:
   - Report ROM file size and memory usage (ARM9 + ARM7 binary sizes)
   - If DeSmuME MCP is available, load ROM with `nds_load_rom`
   - Take an `nds_screenshot` to verify visual output on both screens
5. Report success/failure with structured output

---

**If `test`:**
1. Check for `tests/` directory
2. If `test_config.json` exists, load memory addresses and test plans
3. Run ALL module tests in sequence:
   - If JSON test plans exist: use `nds_run_test` for each
   - If builtin test names match: use `nds_run_builtin_test`
   - If no formal tests exist, run the standard E2E protocol:
     a. `nds_load_rom` → verify ROM loads
     b. `nds_advance_frames(120)` → verify game boots without crash
     c. `nds_screenshot` → verify visual output on both screens
     d. `nds_detect_state` → verify game reaches expected state
     e. `nds_read_memory` → verify key game state values
     f. `nds_touch_screen` → verify touch input works (if applicable)
     g. `nds_press_button` → verify button input works
4. Report results per module in standard format:
   ```
   ═══════════════════════════════════════
     NDS Test Report: <project>
   ═══════════════════════════════════════
   Module 1: Display Setup
     PASS Display mode set correctly (main engine)
     PASS Sub engine initialized
     PASS VRAM banks mapped
   Module 2: Player Sprite
     PASS OAM slot 0 visible on main screen
     PASS Sprite at expected position
     FAIL Animation frame incorrect — expected 2, got 0
   Module 3: Input Handling
     PASS D-pad input registered
     PASS Touch screen tap at (128,96) registered
   ───────────────────────────────────────
   Results: N PASS | N FAIL | N SKIP
   ───────────────────────────────────────
   ```

---

**If `docs`:**
1. Read all source files in `arm9/source/` and `arm7/source/`
2. Identify game entities, mechanics, controls, memory layout, VRAM bank assignments
3. Generate/update:
   - `docs/GAMEPLAY.md` — Game mechanics, controls (buttons + touch), dual-screen layout
   - `docs/TECHNICAL.md` — Memory layout, ARM9/ARM7 split, VRAM bank map, performance
   - `docs/MCP-TOOLS.md` — Memory addresses for testing via MCP tools
4. Use the docs-generator.md reference for format
5. Verify memory addresses against `.map` file if available

---

**If `asset <file>`:**
1. Detect file type from extension:
   - `.png`, `.bmp` → graphics (use grit with NDS flags)
   - `.xm`, `.mod`, `.s3m`, `.it` → music (use mmutil)
   - `.wav` → sound effect (use mmutil)
2. Detect target screen and purpose:
   - Main engine sprite: `-gB8 -Mw<W> -Mh<H> -p` (8bpp indexed)
   - Sub engine sprite: same flags, load to sub engine OAM
   - Main engine BG tileset: `-gB8 -mRtf -p` (tile-reduced)
   - Sub engine BG tileset: same flags, mapped to sub engine VRAM
   - Bitmap (direct): `-gB16 -gb` (16bpp bitmap, rare on NDS)
3. For NitroFS projects, place converted assets in `data/nitrofiles/`:
   - Graphics as `.bin` files loaded at runtime
   - Audio as soundbank for maxmod
4. For compiled-in assets, output `.s` and `.h` to appropriate arm9/arm7 data dirs
5. Report conversion results and generated files

### Step 3: Execute and Report
- Always report what was done in structured format
- On errors, provide specific fix suggestions
- Screenshot the running ROM when possible (via MCP) — always capture both screens
- After completing all work, suggest running `/research-perplexity` for strategic next steps

## Research Gates Reference

These decision points MUST use `/research-perplexity` before proceeding:

| Decision Point | When | What to Research |
|---------------|------|-----------------|
| Architecture Selection | Before Module 1 | Best NDS patterns for this genre, dual-screen strategy, VRAM bank plan |
| Dual-Screen Layout | Before Module 1 + 5 | What content on which screen, touch vs display, sub-screen purpose |
| Sprite Design | Before sprite modules | Sprite sizes, animation frames, palette strategy, which engine |
| Touch Interaction | Before Module 3 | Touch zones, gesture recognition, stylus vs thumb, coordinate mapping |
| Tilemap Design | Before tilemap modules | Tile size, map dimensions, scrolling approach, extended palettes |
| Combat Formula | Before combat modules | Damage calculation, hitbox design, frame timing |
| ARM7/ARM9 Split | Before Module 9 | Audio on ARM7 vs ARM9, FIFO messaging, maxmod integration |
| Save Structure | Before save module | libfat for SD (homebrew) vs EEPROM/Flash (cart), data layout |
| Audio Strategy | Before audio modules | 16-channel allocation, mixing rate, maxmod sequenced vs streaming |
| Hardware Uncertainty | Any time | When unsure about an NDS hardware constraint or register behavior |

## E2E Test Protocol (Per Module)

After each module is built, run these checks:

```
1. make                → compile succeeds (both ARM9 + ARM7, zero errors)
2. ndstool             → ROM packages correctly (.nds file created)
3. nds_load_rom        → ROM loads in DeSmuME without crash
4. nds_advance_frames  → game runs stable for 120+ frames
5. nds_screenshot      → visual output on both screens matches expectations
6. nds_read_memory     → game state values match expected
7. nds_touch_screen    → touch input works correctly (if applicable)
8. [module-specific]   → custom assertions per module
```

## NDS Hardware Quick Reference

- **CPU:** ARM946E-S (67 MHz, ARM9) + ARM7TDMI (33 MHz, ARM7)
- **RAM:** 4MB main RAM (ARM9), 64KB WRAM (shared), 64KB ARM7 WRAM
- **VRAM:** 656KB total across banks A-I (flexible mapping)
- **Display:** Two 256x192 screens, each with 2D+3D engines
- **Main engine:** BG0-3, OBJ, optional 3D on BG0
- **Sub engine:** BG0-3, OBJ (2D only)
- **OAM:** 128 sprites per engine (1KB each)
- **Touch screen:** Resistive, bottom screen only, 256x192 resolution
- **Sound:** 16 channels, 8 PSG + 8 PCM (managed by ARM7)
- **Save:** EEPROM (4-64KB), Flash (256-512KB), or libfat for SD (homebrew)
- **NitroFS:** Filesystem-in-ROM, accessed via `nitroFSInit()` + standard fopen/fread
- **IPC:** ARM9<->ARM7 communication via FIFO registers

## VRAM Bank Mapping Reference

| Bank | Size | Common Mapping |
|------|------|----------------|
| A | 128KB | Main BG (LCDC slot 0) |
| B | 128KB | Main BG (LCDC slot 1) or Main OBJ |
| C | 128KB | Sub BG (ARM7 slot 0) |
| D | 128KB | Main OBJ (LCDC slot 2) or Sub BG |
| E | 64KB | Main BG palette ext / Main OBJ |
| F | 16KB | Main BG palette ext (slots) |
| G | 16KB | Main BG palette ext (slots) |
| H | 32KB | Sub BG |
| I | 16KB | Sub OBJ |

## MCP Tools Reference

All NDS testing uses these MCP tools (registered as `nds-emulator` in `~/.claude/settings.json`):

| Tool | Description |
|------|-------------|
| `nds_load_rom` | Load a .nds ROM into DeSmuME |
| `nds_screenshot` | Capture both screens (top + bottom) |
| `nds_read_memory` | Read memory at address (ARM9 address space) |
| `nds_write_memory` | Write memory at address |
| `nds_press_button` | Press a button (A, B, X, Y, L, R, Start, Select, Up, Down, Left, Right) |
| `nds_touch_screen` | Tap or drag on the touch screen (x, y coordinates) |
| `nds_advance_frames` | Advance N frames (for timing and automation) |
| `nds_detect_state` | Detect current game state |
| `nds_run_test` | Run a custom JSON test plan |
| `nds_run_builtin_test` | Run a named builtin test suite |
| `nds_save_state` | Save emulator state to slot |
| `nds_load_state` | Load emulator state from slot |

**Note:** Unlike GBA, there is no separate `nds_read_oam`, `nds_read_io`, `nds_read_tilemap`, `nds_read_palette`, `nds_profile_frame`, or `nds_check_vblank_budget` tool. Use `nds_read_memory` with the appropriate hardware register addresses for equivalent functionality. Use `nds_advance_frames` with timing analysis for performance profiling.

## Prerequisites
- **devkitPro** installed: `pacman -S nds-dev` (installs devkitARM, libnds, default arm7, ndstool)
- **DeSmuME** running with MCP server (TCP on configured port)
- MCP server registered globally as `nds-emulator` in `~/.claude/settings.json`
- **Optional:** libfat (for SD card save support in homebrew)
- **Optional:** maxmod (for sequenced audio, included in nds-dev)

## Examples

```bash
# Create a new libnds project
/nds-build new my-ds-game

# Build a full game with research-driven modular workflow
/nds-build develop "a dual-screen puzzle game with touch controls"

# Build the current project
/nds-build build

# Run all module tests
/nds-build test

# Generate documentation
/nds-build docs

# Convert a sprite sheet for NDS
/nds-build asset graphics/sprite.png
```
