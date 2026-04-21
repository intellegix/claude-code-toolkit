# Research: /raken-api Command Design
**Date**: 2026-04-21
**Query**: Design global /raken-api context-loader command
**Source**: /research-perplexity

## Key Findings

### Recommended Architecture: Two-Tier Hybrid
1. **Command** (`/raken-api`): Manually invoked context-loader with compiled cache
2. **Rule** (`raken-api.md`): Auto-triggered lightweight guardrail on Raken-related files

### Performance Strategy
- Compiled cache (`raken-api-reference.md`) built from all source docs on first run
- 7-day TTL with modification date check + `--rebuild` flag
- PDF read once during build, never again
- CSV (1807 lines) transformed to ~600-900 lines of structured markdown
- Argument filtering for focused context (e.g., `/raken-api timeCards`)

### Integration with /raken-perplexity
- Keep independent — don't auto-invoke
- Add preamble check to /raken-perplexity suggesting /raken-api first
- /raken-api = local docs, /raken-perplexity = external research

### Risks & Mitigations
- Cache staleness: 7-day TTL + source file mod-date check + `--rebuild`
- Token expiry: Show token age in confirmation, warn if >8 hours
- Path hardcoded: Use find as fallback
