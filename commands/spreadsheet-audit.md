# /spreadsheet-audit — Comprehensive Excel Spreadsheet Audit

Perform a 6-step audit of an Excel spreadsheet for formula correctness, formatting consistency, data integrity, and spec compliance. Uses the `excel-screenshot` MCP server tools — no Excel installation required.

**Architecture**: Validate → Discover → Load Specs → Deep Audit (4 categories) → Visual Verify → Report. Free, fully local.

**CRITICAL: Execute the full audit silently and present results at the end. Only interact with the user in Step 0 (file selection) and Step 2 (spec clarification if no specs found).**

## Input

`$ARGUMENTS` = path to `.xlsx` file (required), optionally followed by sheet name(s) or `--focus` flag.

Examples:
- /spreadsheet-audit "C:\path\to\budget.xlsx"
- /spreadsheet-audit "C:\path\to\report.xlsx" Sheet1
- /spreadsheet-audit "C:\path\to\data.xlsx" --focus formulas

---

## Step 0: Validate Input — MANDATORY, SILENT

1. Parse `$ARGUMENTS` for file path (first argument = file path, remaining = sheet names or `--focus` flag)
2. If no path provided: `Glob` for **/*.xlsx in working directory
   - If exactly 1 found → use it (confirm with user)
   - If 0 found → STOP: "No .xlsx files found. Provide a path."
   - If 2+ found → use `AskUserQuestion` to ask user to pick one (list all found)
3. Verify file exists and is readable by calling spreadsheet_list_sheets(file_path)
4. If file is locked (PermissionError): report "Close Excel first, then retry"
5. If file is password-protected (InvalidFileException): STOP: "File is password-protected. Remove protection first."

---

## Step 1: Discover Spreadsheet Structure — SILENT

1. spreadsheet_list_sheets(file_path) → get all sheet names + dimensions
2. For each sheet:
   - spreadsheet_get_structure(file_path, sheet_name) → merged cells, column widths, row heights, freeze panes
3. Build a structural summary (skip sheets with 0 data rows — note them as "empty"):
   ```
   File: budget.xlsx
   Sheets: 4 (3 with data, 1 empty)
     - Summary (A1:P86) — 12 merged cells, freeze at B2
     - Revenue (A1:H45) — 0 merged, freeze at A2
     - Expenses (A1:L120) — 3 merged, no freeze
     - Charts (no data — skipped)
   ```
4. If `$ARGUMENTS` specifies sheet name(s), filter to those only
5. For very wide sheets (>50 columns), note that column-range chunking may be needed in Step 3

---

## Step 2: Load Spec Constraints

Search for specs in priority order:
1. Check **project-level** CLAUDE.md for **## Excel Specs** or **## Spreadsheet** section
2. Check **global** CLAUDE.md (~/.claude/CLAUDE.md) for the same sections
3. `Glob` for `spreadsheet-spec.md`, `excel-spec.md`, or *-spec.md in the working directory
4. If specs found, parse for these constraint types:
   - **sheets**: Required sheet names (list)
   - **columns**: Expected column headers per sheet, with optional type annotation (currency, percentage, date, text, formula)
   - **formats**: Required number formats per column type (e.g., currency → $#,##0.00)
   - **formulas**: Expected formula patterns per column (e.g., "Column H = SUM of B:G for each row")
   - **row_range**: Expected data row count or range (e.g., "12 monthly rows")
   - **style**: Formatting rules (headers bold, font size, fill colors)
5. If **NO specs found anywhere**:
   - Use `AskUserQuestion` to ask:
     ```
     "No Excel specs found in CLAUDE.md or project docs. What conventions should this spreadsheet follow?"
     Options:
       A) Standard business format (bold headers, currency formatting, SUM totals) (Recommended)
       B) Let me describe the specs now (free text)
       C) Skip spec compliance — audit formulas, formatting, and data only
     ```
   - If user chooses B: collect their description and use it as the spec
   - If user chooses A: use sensible defaults (defined below)
   - If user chooses C: skip Step 3D entirely

**Standard business format defaults** (option A):
- Row 1 = headers: bold, background fill, centered
- Number columns: consistent decimal places within a column
- Currency columns: $#,##0.00 or similar currency format
- Percentage columns: `0.00%` format
- Date columns: consistent date format (mm/dd/yyyy or yyyy-mm-dd)
- Last row of numeric sections: SUM formula or total indicator
- No blank rows in the middle of data ranges
- Consistent font size throughout (exceptions: headers may be larger)

---

## Step 3: Deep Audit — 4 Categories

**Large sheet strategy**: If a sheet has >200 rows, read in chunks of 100 rows with a 5-row overlap buffer (rows 1-105, 100-205, 200-305, etc.) to avoid breaking patterns at chunk boundaries. Accumulate a **running pattern dictionary** across all chunks — do NOT analyze each chunk independently. Always read the first 5 rows (headers + sample data) in one call to establish column patterns before chunking. For very wide sheets (>50 columns), also chunk by column ranges. Deduplicate findings from overlap rows.

For each sheet (filtered by $ARGUMENTS or all):

### 3A: Formula Validation

Read full sheet data with formulas:
spreadsheet_read_range(file_path, sheet_name, used_range, include_formatting=False) — get values + formulas

**Core technique — Formula Normalization**: For each formula in a column, replace relative row numbers with {R} placeholders (e.g., =SUM(B5:G5) → =SUM(B{R}:G{R})). The most common normalized pattern in a column is the "expected" pattern. Any cell that deviates is flagged.

**Pre-classification**: Before normalizing, classify each formula into one of these types:
- **Relative**: Standard row-relative formulas → apply {R} normalization
- **Absolute-anchor**: Contains **$** dollar-sign locks on rows and columns (absolute references) → do NOT replace locked row numbers, only relative ones
- **Named range**: References named ranges (no cell addresses) → skip normalization, treat as its own pattern class
- **Structured table**: Uses [@Column] syntax → skip normalization, treat as its own pattern class
- **Dynamic**: Contains INDIRECT, OFFSET, or INDEX → flag as [INFO] "dynamic formula — manual review recommended", do not pattern-match

Check for:
1. **Hardcoded values in formula columns** — Per-column check: if a column's majority (>60%) cells contain formulas, flag any cell in that column with a raw literal value as "potential hardcoded override" [WARNING]. Columns that are 100% literal values are normal data columns — skip them entirely.
2. **Broken formula patterns** — After normalizing formulas (row→{R}), find the majority pattern per column via counting. Flag any formula that doesn't match the majority as "formula inconsistency" [WARNING]. If only 1 cell out of 20+ deviates, flag as [INFO] (likely intentional override).
3. **Skipped row references** — If a formula in row N references cells in row M (where M != N and the column pattern is self-referential), flag as "formula references wrong row" [CRITICAL]. Parse cell references from formulas and compare to the cell's own row.
4. **Missing totals** — If a numeric column has 3+ data rows but no SUM/AVERAGE/COUNT in the last row or a row labeled "Total", flag as "missing summary formula" [INFO].
5. **Cross-sheet reference integrity** — Extract sheet names from formulas using regex for 'SheetName'! references. Verify those sheets exist in the workbook. Flag broken references as [CRITICAL].
6. **Arithmetic neighbor check** — For cells with raw numeric values in data regions with 5+ consecutive rows: check if the value equals the sum, difference, or product of its immediate left/right/above neighbors. If it does, suggest it should be a formula [INFO]. Only flag when the arithmetic match is exact (within 0.001 tolerance). Skip date columns and section header/subtotal rows.

For each finding, record: sheet, cell, issue, severity, current value, expected pattern.

### 3B: Formatting Consistency

Read formatting data:
spreadsheet_read_range(file_path, sheet_name, used_range, include_formatting=True) — get formatting

**Core technique — Majority Format Detection**: For each formatting property per column, count occurrences of each distinct value. The most common value is the "expected" format. Any cell deviating from the majority is flagged. This avoids hardcoding format expectations.

Check for:
1. **Header row consistency** — All cells in row 1 (or the detected header row) should share: same font size, same bold state, same fill color, same alignment. Flag any header cell that breaks the pattern [WARNING].
2. **Column number_format consistency** — Within each column's data cells, `number_format` should be uniform. Use counting: collect all formats in a column, flag any cell whose format differs from the majority [WARNING]. Common smells: mixing currency format with plain `0.00`, or `0%` with `0.00%` in the same column.
3. **Font size consistency** — Data cells (rows 2+) should share the same `font_size`. Allow headers to differ. Flag outliers [INFO].
4. **Alignment consistency** — Check per column: numeric columns should be consistently aligned (usually right), text columns left. Flag mixed alignment within a column [INFO].
5. **Border consistency** — If borders are used anywhere on the sheet, check for pattern: all data cells should have matching border styles. Missing borders in an otherwise bordered region are flagged [INFO].
6. **Merged cell anti-patterns** — Flag merged cells at or below the data start row (row 2 or first non-header row) as [INFO] — they can break sorting/filtering, but are common for label groupings. Merged cells in header row(s) are acceptable and not flagged.
7. **Fill color consistency** — If alternating row colors are used (zebra striping), verify the even/odd pattern holds throughout. Broken zebra patterns flagged [INFO].

For each finding: sheet, range, issue, severity, actual format, expected format.

### 3C: Data Integrity

Using the values already read:

1. **Missing values** — Cells that are None/empty in an otherwise populated column. Determine column "population rate": if >90% of cells have values, flag empty cells [WARNING]. If 50-90% populated, flag as [INFO]. If <50% populated, skip — column is likely intentionally sparse.
2. **Type mismatches** — Determine column type by majority: if >70% of values are numeric, flag any text values (e.g., "N/A", "TBD", "-") as [WARNING]. Common false positives: header rows, total rows with labels.
3. **Duplicates** — Check the first column and any column whose header contains "ID", "Name", "Key", or "Code" for duplicate values. Flag as [CRITICAL] — duplicate identifiers cause data integrity failures.
4. **Out-of-range values** — Negative numbers in columns formatted as currency (should be positive or use parentheses), percentages > 100% or < 0%, dates in the future for columns that appear historical [INFO].
5. **Cross-sheet data consistency** — If a cell on Sheet A references or mirrors a value on Sheet B (same label in the same row/column header), compare the values. Mismatches flagged as [CRITICAL].
6. **Row continuity** — Blank rows in the middle of a data range (breaks table detection, sorting, and filtering). Flag as [WARNING]. Exclude intentional section separators (rows where the first column has text like "Section" or is bold).
7. **Column header presence** — Every column with data should have a non-empty header in row 1. Missing headers flagged as [WARNING].

### 3D: Spec Compliance

Skip this section entirely if user chose option C in Step 2 (no spec compliance).

Using specs from Step 2:

1. **Required sheets present** — All sheets named in the spec exist. Missing sheet = [CRITICAL].
2. **Column headers match** — Expected headers appear in the correct positions. Missing header = [CRITICAL]. Wrong order = [WARNING]. Extra unlisted columns = [INFO].
3. **Row count within range** — Data rows match expected count (within 10% tolerance unless spec says exact). Out of range = [WARNING].
4. **Number formats match spec** — Currency/percentage/date columns use the specified format. Wrong format = [WARNING].
5. **Formula patterns match** — Specified formula columns use the expected formula type. Use formula normalization (row→{R}) to compare against spec pattern. Mismatch = [CRITICAL].
6. **Style rules match** — If spec defines header style (bold, fill color, font size), verify. Mismatch = [WARNING].
7. **Custom rules** — Any additional user-specified constraints from the spec.

---

## Step 4: Visual Verification via Screenshots

**Key: Use scale=2.0 (192 DPI)** — optimal for AI vision analysis of spreadsheet content. Screenshot only regions with findings, not entire sheets.

For each sheet with findings:
1. **Targeted screenshots only** — Don't screenshot the entire sheet. Instead:
   - Screenshot the header row area (row 1 + first 3 data rows) for every audited sheet
   - For each finding cluster, screenshot the specific range containing the issue (plus 2 rows/cols for context)
   - Use spreadsheet_screenshot(file_path, sheet_name, range, scale=2.0) → render PNG to a temp path
2. `Read` the screenshot (multimodal) — describe what is visually apparent:
   - Are headers visually distinct from data?
   - Do number columns look consistently formatted?
   - Are there visible gaps or misaligned cells?
   - Do colors/fills look consistent?
   - Does the flagged cell actually look problematic, or does it appear intentional?
3. **Visual override (layout only)** — Visual override may ONLY downgrade **layout** findings (merged cells, column widths, row gaps). Never visually override formula or number_format findings — the raw data is more reliable than the rendering (which doesn't render conditional formatting, custom fonts, or exact Excel number display). Note discrepancies without changing severity for formula/format issues.
4. **Skip screenshots if zero findings** — If a sheet passes all checks cleanly, skip visual verification for that sheet entirely.

---

## Step 5: Generate Report

### 5A: Inline Summary (always displayed to user)

```markdown
## Spreadsheet Audit: {filename}
**Date**: {ISO 8601}
**Sheets audited**: {n}
**Cells scanned**: {total}

| Category | Issues | Critical | Warning | Info |
|----------|--------|----------|---------|------|
| Formulas | {n} | {n} | {n} | {n} |
| Formatting | {n} | {n} | {n} | {n} |
| Data Integrity | {n} | {n} | {n} | {n} |
| Spec Compliance | {n} | {n} | {n} | {n} |
| **Total** | **{n}** | **{n}** | **{n}** | **{n}** |

### Top Issues
1. [CRITICAL] {sheet}!{cell}: {description}
2. [WARNING] {sheet}!{cell}: {description}
...
```

**Severity levels**:
- **CRITICAL**: Will produce wrong numbers or errors — broken formulas, skipped row references, broken cross-sheet refs, duplicate IDs, missing required sheets/headers from spec
- **WARNING**: May be an error or spec violation — hardcoded values in formula columns, inconsistent number formats, missing values in well-populated columns, format mismatches vs spec
- **INFO**: Style inconsistency or improvement suggestion — missing totals, font/alignment outliers, merged cells in data area, arithmetic neighbor suggestions, single-cell formula deviations

### 5B: Detailed Report File

Save to {working_directory}/audit_{filename}_{YYYY-MM-DD_HHmm}.md (timestamp ensures no conflicts on re-runs):

```markdown
# Spreadsheet Audit Report

**File**: {absolute_path}
**Date**: {ISO 8601}
**Sheets**: {list}
**Specs**: {source or "standard business defaults" or "none (spec compliance skipped)"}

## Structure Summary
{from Step 1}

## Formula Findings
| Sheet | Cell | Severity | Issue | Current | Expected |
|-------|------|----------|-------|---------|----------|
{findings from 3A}

## Formatting Findings
| Sheet | Range | Severity | Issue | Actual | Expected |
|-------|-------|----------|-------|--------|----------|
{findings from 3B}

## Data Integrity Findings
| Sheet | Cell | Severity | Issue | Value | Context |
|-------|------|----------|-------|-------|---------|
{findings from 3C}

## Spec Compliance
| Rule | Status | Severity | Details |
|------|--------|----------|---------|
{findings from 3D}

## Visual Verification
{Screenshot descriptions + any discrepancies from Step 4}

## Recommendations
1. {Prioritized fix suggestions — CRITICAL first, then WARNING, then INFO}
```

---

## MCP Tools Reference

| Tool | Purpose |
|------|---------|
| spreadsheet_list_sheets(file_path) | Sheet enumeration + dimensions |
| spreadsheet_get_structure(file_path, sheet_name) | Merged cells, column widths, freeze panes |
| spreadsheet_read_range(file_path, sheet_name, range, include_formatting) | Values + formulas + formatting (2D arrays) |
| spreadsheet_screenshot(file_path, sheet_name, range, save_path, scale) | Visual PNG rendering — **always use scale=2.0** |

---

## Error Handling

| Error | Action |
|-------|--------|
| No .xlsx files found | STOP: "No .xlsx files found. Provide a path." |
| File locked (PermissionError) | STOP: "Close Excel first, then retry." |
| File password-protected | STOP: "File is password-protected. Remove protection first." |
| MCP tool not available | STOP: "excel-screenshot MCP server not found. Verify it's configured in settings." |
| Sheet not found (from $ARGUMENTS) | Report which sheets exist and ask user to pick |
| Empty workbook (all sheets empty) | Report "Workbook contains no data — nothing to audit." |
| Screenshot render fails | Skip visual verification for that range, note in report |

---

## Key Techniques Reference

1. **Formula normalization**: Replace RELATIVE row numbers only with {R} — preserve absolute refs (dollar-sign locks on rows and columns). Pre-classify formulas into: relative, absolute-anchor, named-range, structured-table, dynamic (INDIRECT/OFFSET).
2. **Skipped row detection**: Parse cell references from formulas. If a formula in row 10 references row 8, it's likely a copy-paste error.
3. **Cross-sheet regex**: Look for patterns like 'SheetName'! or SheetName! in formulas to extract referenced sheet names.
4. **Arithmetic neighbor check**: Scope to data regions with 5+ consecutive rows. Skip date columns and section headers/subtotals. Test sum, difference, product of immediate neighbors.
5. **Counter-based majority detection**: For both formulas and formatting properties, the majority value in a column IS the expected value. Minority values are the findings.
6. **Merged cell boundary**: Data start row is the boundary. Merges above = OK, merges at/below = INFO-level note.
7. **Visual scale**: `scale=2.0` (192 DPI) is optimal for AI multimodal analysis. Visual override restricted to layout issues only.
8. **Chunk overlap**: 5-row overlap buffer at chunk boundaries + accumulated cross-chunk pattern state.
9. **Severity calibration**: CRITICAL = produces wrong numbers/errors. WARNING = may be an error. INFO = style suggestion.
