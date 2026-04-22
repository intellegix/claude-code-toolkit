# /spreadsheet-audit — Comprehensive Excel Spreadsheet Audit

Perform a 6-step audit of an Excel spreadsheet for formula correctness, formatting consistency, data integrity, boss-auditable simplicity, and spec compliance. Uses the `excel-screenshot` MCP server tools — no Excel installation required.

**Architecture**: Validate → Discover → Load Specs → Deep Audit (5 categories) → Visual Verify → Report. Free, fully local.

**BOSS-AUDITABLE PRINCIPLE**: Every formula in the workbook must be understandable by a non-technical person who clicks the cell. Only simple arithmetic (+, -, *, /), plain cell references, and small SUM() are allowed. Time entry totals must show each individual entry as an explicit addend (=8+8+8, never =SUM(range) or =24). This rule is enforced in Step 3E and cross-checked in Steps 3A and 3D.

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
- **Dynamic**: Contains INDIRECT, OFFSET, or INDEX → flag as [CRITICAL] "banned complex function — not boss-auditable", do not pattern-match
- **Banned function**: Contains any function from the banned list (see 3E) → flag as [CRITICAL] "banned function — rewrite as simple arithmetic"

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

### 3E: Boss-Auditable Formula Simplicity

**PURPOSE**: Ensure every formula is understandable by a non-technical boss who clicks the cell. This is not optional — it is the highest-priority audit category. A formula that produces the right number but cannot be visually understood by a layperson is a CRITICAL finding.

#### Allowed Formulas (whitelist)

Only these formula patterns are permitted:

1. **Simple arithmetic**: =A5+B5, =C3-D3, =E2*F2, =G7/H7, and combinations like =A1+B1-C1
2. **Plain cell references**: =A5, =Sheet1!B3 (single cell, no functions)
3. **Explicit addend chains**: =8+8+8+4, =10.5+8+7.5 (literal numbers joined by +)
4. **Small SUM()**: =SUM(A1,A2,A3) or =SUM(A1:A5) where the range spans 10 or fewer cells. SUM is the ONLY allowed function.
5. **Simple cross-sheet references**: =Sheet1!B5, ='Other Sheet'!C10 (plain reference, no functions wrapping it)

#### Banned Functions (comprehensive list)

Any formula containing these functions is flagged [CRITICAL] with a suggested simple rewrite. **Note**: Excel 2013+ prefixes newer functions with _xlfn. or _xlws. in the stored formula (e.g., _xlfn.XLOOKUP, _xlfn.IFS, _xlfn.CONCAT). Always strip these prefixes before checking the banned list — they are invisible to the user but present in openpyxl formula strings.

**Lookup/Reference** (boss cannot trace data flow):
VLOOKUP, HLOOKUP, XLOOKUP, INDEX, MATCH, CHOOSE, INDIRECT, OFFSET, ROW, COLUMN, ADDRESS, AREAS, LOOKUP

**Conditional aggregation** (hides which rows are included):
SUMIF, SUMIFS, COUNTIF, COUNTIFS, AVERAGEIF, AVERAGEIFS, SUMPRODUCT, DSUM, DCOUNT, DAVERAGE, MAXIFS, MINIFS

**Logic/nesting** (branches confuse non-technical readers):
IF (nested — a single flat IF like =IF(A1>0,A1,0) is borderline [WARNING], nested IF is [CRITICAL]), IFS, SWITCH, AND, OR, NOT, IFERROR, IFNA, ISERROR, ISBLANK, ISNA

**Text manipulation** (boss expects to see text, not text formulas):
CONCATENATE, CONCAT, TEXTJOIN, LEFT, RIGHT, MID, LEN, FIND, SEARCH, SUBSTITUTE, REPLACE, TEXT, TRIM, CLEAN, UPPER, LOWER, PROPER, REPT, VALUE, NUMBERVALUE

**Array/dynamic** (completely opaque to non-technical users):
Any formula wrapped in curly braces (array formula), FILTER, SORT, SORTBY, UNIQUE, SEQUENCE, RANDARRAY, LET, LAMBDA, MAP, REDUCE, SCAN, MAKEARRAY, BYCOL, BYROW

**Date/time functions** (prefer explicit values):
DATE, DATEVALUE, TODAY, NOW, YEAR, MONTH, DAY, WEEKDAY, WEEKNUM, NETWORKDAYS, WORKDAY, EDATE, EOMONTH, DATEDIF

**Math beyond basics** (boss should see the arithmetic):
ROUND, ROUNDUP, ROUNDDOWN, CEILING, FLOOR, MOD, ABS, SIGN, INT, TRUNC, POWER, SQRT, LOG, LN, EXP, FACT, PRODUCT, AGGREGATE, SUBTOTAL

**Statistical** (hides which values are aggregated):
AVERAGE (use explicit addend chain divided by count instead), MEDIAN, MODE, STDEV, VAR, MIN, MAX, LARGE, SMALL, PERCENTILE, QUARTILE, COUNT, COUNTA, COUNTBLANK, RANK

#### Detection Method

**Primary: openpyxl Tokenizer** — use the openpyxl formula tokenizer for structural classification. This is more robust than regex alone for nested formulas and edge cases.

```python
from openpyxl.formula import Tokenizer

def classify_formula(formula_text):
    """Classify a formula for boss-auditability using openpyxl Tokenizer."""
    tok = Tokenizer(formula_text)
    functions_found = []
    nesting_depth = 0
    max_nesting = 0
    is_array = False

    for t in tok.items:
        if t.type == 'FUNC' and t.subtype == 'OPEN':
            func_name = t.value.rstrip('(').replace('_xlfn.', '').replace('_xlws.', '')
            functions_found.append(func_name)
            nesting_depth += 1
            max_nesting = max(max_nesting, nesting_depth)
        elif t.type == 'FUNC' and t.subtype == 'CLOSE':
            nesting_depth -= 1
        elif t.type == 'ARRAY':
            is_array = True

    return functions_found, max_nesting, is_array
```

**Supplementary: regex fallback** — for formulas the Tokenizer cannot parse (malformed, external add-in functions), fall back to regex extraction. Pattern: match any uppercase word immediately followed by an opening parenthesis. Strip the _xlfn. and _xlws. prefixes that Excel 2013+ adds to newer functions before checking the banned list.

For every formula cell in the workbook:

1. **Tokenize the formula**: Run the Tokenizer to extract function names, nesting depth, and array status. If the Tokenizer raises an exception, fall back to regex extraction.
2. **Strip Excel prefixes**: Remove _xlfn. and _xlws. prefixes from function names before checking the banned list. These prefixes appear on newer functions like XLOOKUP, FILTER, CONCAT, IFS, SWITCH, MAXIFS, MINIFS, TEXTJOIN, and others.
3. **Check against banned list**: If any extracted function name appears in the banned list above, flag the cell as [CRITICAL].
4. **Check SUM range size** (tiered rules):

| SUM Pattern | Cells | Severity | Action |
|-------------|-------|----------|--------|
| Explicit args: SUM(A1,A2,A3) | 2-5 | PASS | No finding |
| Explicit args: SUM(A1,A2,...,A8) | 6-10 | PASS with NOTE | "Boss can verify but consider explicit addends" |
| Contiguous range: SUM(A1:A10) | up to 10 | [WARNING] | "Range hides individual values — prefer explicit addends" |
| Any SUM pattern | 11-50 | [WARNING] | "SUM range too large — break into smaller explicit sums" |
| Any SUM pattern | 51+ | [CRITICAL] | "SUM range far too large for audit — must restructure" |
| Named range: SUM(HoursWorked) | any | [CRITICAL] | "Named range hides both source and count" |

5. **Check for array formulas**: Two detection methods:
   - **Cell-level**: If the formula text is wrapped in curly braces (legacy CSE array formula), flag as [CRITICAL]
   - **Sheet-level**: Check the worksheet's array_formulae property (openpyxl exposes this as ws.array_formulae) for any array formula ranges that include the current cell. Flag as [CRITICAL] "legacy array formula — completely opaque to non-technical users"
   - **Dynamic arrays**: If the formula contains FILTER, SORT, SORTBY, UNIQUE, SEQUENCE, RANDARRAY, LET, LAMBDA, MAP, REDUCE, SCAN, flag as [CRITICAL]
6. **Check nesting depth**: Use the Tokenizer's FUNC OPEN/CLOSE token pairs to track actual function nesting (not just parenthesis counting, which over-counts arithmetic grouping). If nesting exceeds 2 levels, flag as [CRITICAL] "formula too deeply nested for non-technical audit." Example: =SUM(A1+B1) is 1 level (OK). =IF(A1>0,SUM(B1,C1),0) is 2 levels (OK). =IF(A1>0,SUM(IF(B1:B10>0,B1:B10)),0) is 3 levels (CRITICAL).
7. **Auto-fix generation**: For deterministic CRITICAL findings, generate a concrete suggested rewrite:
   - Small SUM(range) where all values are known: rewrite as explicit addend chain
   - Single ROUND wrapping simple arithmetic: remove ROUND, note the rounding in a cell comment instead
   - Single flat IF with simple branches: suggest splitting into two clearly labeled rows

#### Time Entry Explicit-Addend Rule

**This is the most important sub-rule.** When time entries (hours worked) are totaled in a cell, the formula MUST show each individual time entry as a literal number joined by addition. This lets the boss click the cell and see exactly which hours make up the total.

**Detection — identifying time/hours columns**: A column is a "time entry" or "hours" column if ANY of these are true:
- Column header contains: "hours", "hrs", "time", "total hours", "reg", "ot", "dt", "regular", "overtime", "double time", "straight time", "ST", "OT", "DT" (case-insensitive)
- Column header matches a day-of-week pattern: "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Monday", "Tuesday", etc.
- Column header matches a date pattern: "3/10", "03/10", "Mar 10", "2025-03-10", etc.
- The column is in a row context where the row header or adjacent label column contains "hours", "time", "labor"

**Validation for time/hours cells**:
1. If the cell contains a formula that uses SUM() over a range (e.g., =SUM(B5:H5)), flag as [CRITICAL]: "Time entry total uses SUM(range) — boss cannot see individual entries. Rewrite as explicit addends, e.g., =8+8+8+4+8+0+0"
2. If the cell contains a single hardcoded number (e.g., 24) in a totals column where other cells in the same column use formulas, flag as [CRITICAL]: "Time entry total is a hardcoded number — boss cannot verify which days contribute. Rewrite as explicit addends, e.g., =8+8+8"
3. If the cell contains an explicit addend chain (e.g., =8+8+8+4), this is CORRECT — no finding.
4. If the cell contains a formula referencing individual cells with + (e.g., =B5+C5+D5+E5+F5), this is ACCEPTABLE but flag as [INFO]: "Consider using literal values (=8+8+8+4+8) instead of cell references so boss sees actual hours without clicking referenced cells"
5. **Addend count threshold**: If a time total would require more than 31 explicit addends (i.e., more than a full month of daily entries), cell references with + are acceptable without the INFO flag. For 31 or fewer entries, prefer literal addends.

**Suggested rewrites**: For every [CRITICAL] time entry finding, include a concrete rewrite suggestion. Example:
```
[CRITICAL] Sheet1!H5: =SUM(B5:G5) — time total uses SUM(range)
  Current: =SUM(B5:G5) → evaluates to 44
  Rewrite: =8+8+8+8+4+8 (showing Mon=8, Tue=8, Wed=8, Thu=8, Fri=4, Sat=8)
  Reason: Boss can click cell and see each day's hours
```

To build the rewrite: read the values of the referenced cells (B5 through G5), then construct the addend chain from those values.

#### Cross-Sheet Simplicity

Cross-sheet references are allowed ONLY as plain cell references:
- ALLOWED: =Sheet1!B5, ='Payroll Data'!C10
- BANNED: =VLOOKUP(A5,'Payroll Data'!A:C,3,FALSE), =SUMIF(Sheet1!A:A,A5,Sheet1!B:B)

If a formula combines a cross-sheet reference with any banned function, flag as [CRITICAL]: "Complex cross-sheet formula — boss cannot trace data source. Use a plain reference like =Sheet1!B5 instead."

#### Reporting Format for 3E

For each finding, record: sheet, cell, severity, current formula, evaluated value, suggested rewrite, reason.

Group findings into:
- **Banned functions found** (with function name and cell location)
- **Time entry violations** (with current formula and suggested explicit-addend rewrite)
- **SUM range too large** (with range size and suggestion)
- **Excessive nesting** (with nesting depth)
- **Complex cross-sheet formulas** (with referenced sheet and function used)

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
| Boss-Auditable | {n} | {n} | {n} | {n} |
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
- **CRITICAL**: Will produce wrong numbers, errors, OR is not boss-auditable — broken formulas, skipped row references, broken cross-sheet refs, duplicate IDs, missing required sheets/headers from spec, **banned functions**, **time entry totals not shown as explicit addends**, **excessive nesting**, **complex cross-sheet formulas**
- **WARNING**: May be an error or spec violation — hardcoded values in formula columns, inconsistent number formats, missing values in well-populated columns, format mismatches vs spec, **SUM over large ranges (>10 cells)**, **single flat IF statement**
- **INFO**: Style inconsistency or improvement suggestion — missing totals, font/alignment outliers, merged cells in data area, arithmetic neighbor suggestions, single-cell formula deviations, **time entry using cell references instead of literal addends**

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

## Boss-Auditable Simplicity Findings
| Sheet | Cell | Severity | Issue | Current Formula | Suggested Rewrite |
|-------|------|----------|-------|----------------|-------------------|
{findings from 3E — banned functions, time entry violations, large SUM ranges, nesting, complex cross-sheet}

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

1. **Formula normalization**: Replace RELATIVE row numbers only with {R} — preserve absolute refs (dollar-sign locks on rows and columns). Pre-classify formulas into: relative, absolute-anchor, named-range, structured-table, dynamic, banned-function.
2. **Skipped row detection**: Parse cell references from formulas. If a formula in row 10 references row 8, it's likely a copy-paste error.
3. **Cross-sheet regex**: Look for patterns like 'SheetName'! or SheetName! in formulas to extract referenced sheet names.
4. **Arithmetic neighbor check**: Scope to data regions with 5+ consecutive rows. Skip date columns and section headers/subtotals. Test sum, difference, product of immediate neighbors.
5. **Counter-based majority detection**: For both formulas and formatting properties, the majority value in a column IS the expected value. Minority values are the findings.
6. **Merged cell boundary**: Data start row is the boundary. Merges above = OK, merges at/below = INFO-level note.
7. **Visual scale**: `scale=2.0` (192 DPI) is optimal for AI multimodal analysis. Visual override restricted to layout issues only.
8. **Chunk overlap**: 5-row overlap buffer at chunk boundaries + accumulated cross-chunk pattern state.
9. **Severity calibration**: CRITICAL = wrong numbers/errors OR not boss-auditable. WARNING = may be an error. INFO = style suggestion.
10. **Banned function detection**: Primary: openpyxl Tokenizer extracts typed FUNC tokens. Supplementary: regex fallback. Always strip _xlfn. and _xlws. prefixes before checking banned list. SUM is the only allowed function (with tiered range-size rules).
11. **Time entry column detection**: Match column headers against hours/time/day-of-week/date patterns (case-insensitive). Time totals must be explicit addend chains (=8+8+8), never SUM(range) or hardcoded literals.
12. **Explicit addend rewrite**: For flagged time entry cells, read the referenced cell values and construct a replacement formula as literal addends joined by +. Include the rewrite in the finding.
13. **Nesting depth check**: Use Tokenizer FUNC OPEN/CLOSE pairs to track actual function nesting (not parenthesis counting). More than 2 levels = CRITICAL.
14. **Array formula detection**: Two sources: cell-level curly brace wrapping + sheet-level ws.array_formulae property. Both must be checked.
15. **Excel function prefix stripping**: _xlfn. (XLOOKUP, FILTER, IFS, etc.) and _xlws. prefixes must be stripped before banned list comparison. These are invisible to users but present in openpyxl formula strings.
16. **Auto-fix generation**: For deterministic CRITICAL findings (small SUM with known values, single ROUND, single flat IF), generate concrete rewrite suggestions.
