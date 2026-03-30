# Game Profile: Brain Attic

## Identification
- **ROM Title Pattern:** `BRAINATTIC`
- **Guide Path:** `C:/dev/brain-attic/docs/gba-claude-guide.md`
- **Test Config:** `C:/dev/brain-attic/tests/test_config.json`

## MCP Tools
Brain Attic uses ONLY the generic `gba_*` MCP tools. All game state is read via `gba_read_memory`.

## Memory Map — `g_state` at `0x03002A20` (124 bytes, IWRAM)

| Offset | Size | Field | Type | Notes |
|--------|------|-------|------|-------|
| +0x00..+0x53 | 84 | sne.domains[0..6] | DomainState[7] | 12 bytes each: signal(int4), noise(int4), decay_rate(int4) |
| +0x54 | 4 | day_loop.phase | int | 0=MORNING, 1=DAY, 2=EVENING, 3=NIGHT |
| +0x58 | 4 | day_loop.phase_frames | int | Frames elapsed in current phase |
| +0x5C | 4 | day_loop.day_number | int | 0-indexed day counter |
| +0x60 | 1 | day_loop.phase_changed | bool | True for 1 frame after transition |
| +0x61..+0x63 | 3 | (padding) | - | Struct alignment |
| +0x64 | 1 | rooms_visited | uint8 | Bitfield: bit N = room N visited |
| +0x65 | 1 | synthesis_history | uint8 | Bitfield of completed combos |
| +0x66 | 1 | run_seed | uint8 | Random seed for current run |
| +0x67 | 1 | (padding) | - | Alignment for fixed_point |
| +0x68 | 4 | player_pos.x | bn::fixed (int32) | Divide by 4096 for world coord (bn::fixed uses 12 fractional bits) |
| +0x6C | 4 | player_pos.y | bn::fixed (int32) | Divide by 4096 for world coord (bn::fixed uses 12 fractional bits) |
| +0x70 | 4 | current_room | int | 0=HUB, 1=LIBRARY, 2=ENGINEERING, 3=SCIENCE, 4=PHILOSOPHY, 5=BUSINESS |
| +0x74 | 4 | player_facing | int | 0=DOWN, 1=UP, 2=LEFT, 3=RIGHT |
| +0x78 | 1 | in_dialogue | bool | True during dialogue |
| +0x79 | 1 | hud_dirty | bool | True when HUD needs redraw |
| +0x7A | 1 | popup_active | bool | True when popup is showing |
| +0x7B | 1 | (padding) | - | Struct tail alignment |

### Domain Index (for sne.domains[])
Each DomainState is 12 bytes at `g_state + (index * 12)`:
- 0 = GENERAL
- 1 = ENGINEERING
- 2 = LAW
- 3 = SCIENCE
- 4 = HISTORY
- 5 = PHILOSOPHY
- 6 = BUSINESS

### Reading a Domain's Signal
To read ENGINEERING signal: `gba_read_memory(0x03002A20 + 1*12, 4)` = read 4 bytes at `0x03002A2C`

### Reading Player Position
```
x_raw = gba_read_memory(0x03002A88, 4)  # 0x03002A20 + 0x68
y_raw = gba_read_memory(0x03002A8C, 4)  # 0x03002A20 + 0x6C
x_world = x_raw / 4096  (signed int32 / 4096, 12 fractional bits)
y_world = y_raw / 4096
```

**NOTE:** Offsets derived from struct analysis. Run Step 8 (runtime verification) after first build to confirm padding matches actual compiler output.

## Test Recipes

### BA-1: VERIFY_BOOT
1. `gba_get_frame` — ASSERT frame > 0 (emulator running)
2. `gba_advance_frames(120)` — let game initialize
3. `gba_screenshot` — ASSERT visible game screen (not black)

### BA-2: VERIFY_POSITION
1. Read 4 bytes at `0x03002A88` (player_pos.x) — interpret as signed int32
2. Read 4 bytes at `0x03002A8C` (player_pos.y) — interpret as signed int32
3. Divide each by 256 for world coordinates
4. ASSERT x within -120..120, y within -120..120 (Hub floor bounds)

### BA-3: VERIFY_ROOM
1. Read 4 bytes at `0x03002A90` (current_room)
2. ASSERT value == 0 (ATTIC_HUB on fresh start)

### BA-4: VERIFY_DPAD
1. Read player_pos.x (baseline)
2. Hold RIGHT for 30 frames: `gba_press_key("RIGHT")` + `gba_advance_frames(30)`
3. Read player_pos.x again
4. ASSERT new x > baseline x (player moved right)

### BA-5: VERIFY_ROOM_WARP
1. Record current_room (should be 0 = HUB)
2. Walk south toward Library door: hold DOWN for ~80 frames
3. `gba_advance_frames(10)` — let warp trigger
4. Read current_room
5. ASSERT current_room == 1 (LIBRARY)
6. Screenshot to confirm room change

### BA-6: VERIFY_OBJECT_PICKUP
1. Reset to Hub (reload if needed)
2. Read GENERAL domain signal at `0x03002A20` (domains[0].signal, 4 bytes)
3. Walk to Logic Primer at (-40, -20): navigate player toward that position
4. Press A to interact
5. `gba_advance_frames(30)` — let absorption process
6. Read GENERAL domain signal again
7. ASSERT signal increased

### BA-7: VERIFY_DAY_PHASE
1. Read day_loop.phase at `0x03002A74` (should be 0 = MORNING)
2. `gba_advance_frames(650)` — exceed MORNING duration (600 frames)
3. Read day_loop.phase again
4. ASSERT phase > 0 (transitioned past MORNING)

### BA-8: VERIFY_SAVE_LOAD
1. Advance to a known state (day > 0 or object picked up)
2. Read SRAM at offset 0 (4 bytes)
3. If save has occurred, ASSERT magic bytes == 0xBA1C0DE5
4. If no auto-save yet, `gba_advance_frames(3600)` to trigger end-of-day save
5. Re-read SRAM, ASSERT magic == 0xBA1C0DE5

### BA-9: VERIFY_PAUSE_MENU
1. Press START: `gba_press_key("START")` + `gba_advance_frames(10)`
2. `gba_screenshot` — ASSERT menu overlay visible (text elements on screen)
3. Press B to close: `gba_press_key("B")` + `gba_advance_frames(10)`
4. `gba_screenshot` — ASSERT menu gone, gameplay resumed

### BA-10: STRESS_FULL_DAY
1. Read day_loop.day_number at `0x03002A7C`
2. `gba_advance_frames(3600)` — full day cycle (600+1800+900+300)
3. Read day_loop.day_number again
4. ASSERT day_number incremented by 1
5. Screenshot to confirm game still rendering

## Test Modes

### `smoke` — Quick Health Check (~10 tool calls)
Run BA-1, BA-2, BA-3.

### `gameplay` — Core Mechanics (~30 tool calls)
Run BA-4, BA-5, BA-6, BA-7.

### `save` — Persistence (~15 tool calls)
Run BA-8.

### `stress` — Endurance (~20 tool calls)
Run BA-9, BA-10.

### `full` — All Tests (~75 tool calls)
Run all BA-1 through BA-10 in sequence.

## Smoke Report Format
```
| # | Test | Expected | Actual | Result |
|---|------|----------|--------|--------|
| BA-1 | Boot + screenshot | frame > 0, visible screen | ... | PASS/FAIL |
| BA-2 | Player position | within Hub bounds | ... | PASS/FAIL |
| BA-3 | Starting room | room == 0 (HUB) | ... | PASS/FAIL |
```

## Full Report Format
```
| # | Test | Expected | Actual | Result |
|---|------|----------|--------|--------|
| BA-1 | Boot | frame > 0, screen visible | ... | PASS/FAIL |
| BA-2 | Position | Hub bounds (-120..120) | ... | PASS/FAIL |
| BA-3 | Room | 0 (ATTIC_HUB) | ... | PASS/FAIL |
| BA-4 | D-pad | x increased after RIGHT | ... | PASS/FAIL |
| BA-5 | Room warp | room changed to 1 | ... | PASS/FAIL |
| BA-6 | Object pickup | signal increased | ... | PASS/FAIL |
| BA-7 | Day phase | phase > 0 after 650 frames | ... | PASS/FAIL |
| BA-8 | Save/Load | SRAM magic = 0xBA1C0DE5 | ... | PASS/FAIL |
| BA-9 | Pause menu | menu visible, closeable | ... | PASS/FAIL |
| BA-10 | Full day stress | day_number incremented | ... | PASS/FAIL |
```
