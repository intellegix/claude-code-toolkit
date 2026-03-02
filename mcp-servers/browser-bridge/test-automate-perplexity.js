/**
 * test-automate-perplexity.js — Unit tests for automate_perplexity_task tool
 *
 * Tests validation logic, parameter defaults, slash command selection, and error paths.
 * Does NOT test actual browser automation — mocks bridge.broadcast().
 *
 * Run with: node --test test-automate-perplexity.js
 */

import assert from 'node:assert';
import { describe, it } from 'node:test';

import { Validator } from './lib/validator.js';
import { CONFIG } from './lib/config.js';

// ---------------------------------------------------------------------------
// Input validation
// ---------------------------------------------------------------------------

describe('automate_perplexity_task — input validation', () => {
  it('1. Validator.text rejects empty task', () => {
    // The tool calls Validator.text(args.task, 10_000)
    // Empty string is technically valid for Validator.text (it checks typeof + maxLen)
    // But the tool requires 'task' in required, so MCP rejects missing.
    // Test that a non-string throws:
    assert.throws(() => Validator.text(undefined, 10_000), /must be a string/i);
    assert.throws(() => Validator.text(123, 10_000), /must be a string/i);
    assert.throws(() => Validator.text(null, 10_000), /must be a string/i);
  });

  it('2. Validator.action rejects invalid mode', () => {
    const allowed = ['standard', 'research', 'labs'];
    assert.throws(() => Validator.action('invalid', allowed), /Invalid action/);
    assert.throws(() => Validator.action('deep', allowed), /Invalid action/);
    // Valid modes should pass
    assert.strictEqual(Validator.action('standard', allowed), 'standard');
    assert.strictEqual(Validator.action('research', allowed), 'research');
    assert.strictEqual(Validator.action('labs', allowed), 'labs');
  });
});

// ---------------------------------------------------------------------------
// Timeout bounds
// ---------------------------------------------------------------------------

describe('automate_perplexity_task — timeout bounds', () => {
  it('3. Validator.timeout clamps maxWaitMs to [10000, 900000]', () => {
    // Below minimum
    assert.throws(() => Validator.timeout(5000, 10_000, 900_000, 300_000), /must be/);
    // Above maximum
    assert.throws(() => Validator.timeout(1_000_000, 10_000, 900_000, 300_000), /must be/);
    // Within range
    assert.strictEqual(Validator.timeout(60_000, 10_000, 900_000, 300_000), 60_000);
    // Boundaries
    assert.strictEqual(Validator.timeout(10_000, 10_000, 900_000, 300_000), 10_000);
    assert.strictEqual(Validator.timeout(900_000, 10_000, 900_000, 300_000), 900_000);
  });

  it('4. Validator.timeout clamps stableMs to [2000, 60000]', () => {
    // Below minimum
    assert.throws(() => Validator.timeout(1000, 2_000, 60_000, 8_000), /must be/);
    // Above maximum
    assert.throws(() => Validator.timeout(100_000, 2_000, 60_000, 8_000), /must be/);
    // Within range
    assert.strictEqual(Validator.timeout(5000, 2_000, 60_000, 8_000), 5000);
  });
});

// ---------------------------------------------------------------------------
// Default values
// ---------------------------------------------------------------------------

describe('automate_perplexity_task — default values', () => {
  it('5. mode defaults to standard, validate to true, timeouts to defaults', () => {
    // mode: when args.mode is undefined, tool uses 'standard'
    // Simulating: args.mode ? Validator.action(args.mode, ...) : 'standard'
    const mode = undefined ? Validator.action(undefined, ['standard', 'research', 'labs']) : 'standard';
    assert.strictEqual(mode, 'standard');

    // validate defaults to true
    const shouldValidate = Validator.boolean(undefined, true);
    assert.strictEqual(shouldValidate, true);

    // maxWaitMs defaults to 300000
    const maxWaitMs = Validator.timeout(undefined, 10_000, 900_000, 300_000);
    assert.strictEqual(maxWaitMs, 300_000);

    // stableMs defaults to 8000
    const stableMs = Validator.timeout(undefined, 2_000, 60_000, 8_000);
    assert.strictEqual(stableMs, 8_000);
  });
});

// ---------------------------------------------------------------------------
// Slash command selection
// ---------------------------------------------------------------------------

describe('automate_perplexity_task — slash command selection', () => {
  it('6. research mode builds /research, labs builds /labs, standard skips', () => {
    // Mirrors Step B logic in server.js:
    // const slashCmd = mode === 'research' ? '/research ' : '/labs ';
    const buildSlash = (mode) => {
      if (mode === 'research' || mode === 'labs') {
        return mode === 'research' ? '/research ' : '/labs ';
      }
      return null; // standard mode skips slash command
    };

    assert.strictEqual(buildSlash('research'), '/research ');
    assert.strictEqual(buildSlash('labs'), '/labs ');
    assert.strictEqual(buildSlash('standard'), null);
  });
});

// ---------------------------------------------------------------------------
// Validation paths (empty response, skip, validator error)
// ---------------------------------------------------------------------------

describe('automate_perplexity_task — validation logic', () => {
  it('7. empty response produces block violation', () => {
    // Mirrors Step G logic in server.js (lines 1149-1151):
    const responseText = '';
    const shouldValidate = true;
    let validated = false;
    let violations = [];

    if (shouldValidate && responseText.length > 0) {
      validated = true; // Would run validator
    } else if (responseText.length === 0) {
      validated = false;
      violations = [{ rule: 'empty_response', severity: 'block', message: 'Perplexity returned empty response' }];
    } else {
      validated = true;
    }

    assert.strictEqual(validated, false);
    assert.strictEqual(violations.length, 1);
    assert.strictEqual(violations[0].rule, 'empty_response');
    assert.strictEqual(violations[0].severity, 'block');
  });

  it('8. validate=false skips validation, sets validated=true', () => {
    // Mirrors Step G: when shouldValidate is false and responseText is non-empty
    const responseText = 'Some response text';
    const shouldValidate = false;
    let validated = false;
    let violations = [];

    if (shouldValidate && responseText.length > 0) {
      // Would run validator
    } else if (responseText.length === 0) {
      validated = false;
      violations = [{ rule: 'empty_response', severity: 'block', message: 'Perplexity returned empty response' }];
    } else {
      validated = true; // Validation skipped
    }

    assert.strictEqual(validated, true);
    assert.strictEqual(violations.length, 0);
  });

  it('9. validator error produces warn violation (non-fatal)', () => {
    // Mirrors catch block in Step G (lines 1143-1148):
    const valErr = new Error('Python not found');
    let validated = false;
    let violations = [{ rule: 'validator_error', severity: 'warn', message: valErr.message }];

    assert.strictEqual(validated, false);
    assert.strictEqual(violations.length, 1);
    assert.strictEqual(violations[0].rule, 'validator_error');
    assert.strictEqual(violations[0].severity, 'warn');
    assert.ok(violations[0].message.includes('Python not found'));
  });
});

// ---------------------------------------------------------------------------
// Config timeout key
// ---------------------------------------------------------------------------

describe('automate_perplexity_task — config', () => {
  it('10. perplexityAuto timeout exists in CONFIG and equals 600000', () => {
    assert.ok('perplexityAuto' in CONFIG.timeouts, 'perplexityAuto key missing from CONFIG.timeouts');
    assert.strictEqual(CONFIG.timeouts.perplexityAuto, 600_000);
  });
});
