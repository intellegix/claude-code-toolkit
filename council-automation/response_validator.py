"""
Response Validator - Barrier between AI systems.

Validates Perplexity AI responses before Claude consumes them. Checks for:
- Code syntax errors
- Destructive commands
- Response length sanity
- TODO injection (hallucination markers)
- Diff size limits
- Confidence markers (delegation failures)

Usage:
    python response_validator.py --json '{"response":"...","task":"..."}'

Output:
    JSON to stdout: {"valid": bool, "violations": [...], "sanitized_response": "..."}
"""

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass
class Violation:
    """Represents a validation rule violation."""
    rule: str
    severity: Literal["block", "warn"]
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message
        }


@dataclass
class ValidationResult:
    """Result of response validation."""
    valid: bool
    violations: list[Violation]
    sanitized_response: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "violations": [v.to_dict() for v in self.violations],
            "sanitized_response": self.sanitized_response
        }


class ResponseValidator:
    """Validates AI responses against safety and quality rules."""

    def __init__(self, config_path: Path | None = None):
        """Initialize validator with config from file or defaults."""
        if config_path is None:
            config_path = Path(__file__).parent / "validator_config.json"

        self.config = self._load_config(config_path)

    def _load_config(self, config_path: Path) -> dict[str, Any]:
        """Load config from JSON file, fall back to hardcoded defaults."""
        default_config = {
            "min_response_length": 50,
            "max_response_length": 50000,
            "max_todo_count": 3,
            "max_code_lines": 500,
            "destructive_patterns": [
                r"rm\s+-rf",
                r"DROP\s+TABLE",
                r"DROP\s+DATABASE",
                r"git\s+push\s+--force",
                r"git\s+reset\s+--hard",
                r"format\s+[A-Z]:",
                r"del\s+/[sS]\s+/[qQ]",
                r"Remove-Item.*-Recurse.*-Force"
            ],
            "confidence_phrases": [
                "I'm not sure",
                "I don't have access",
                "I cannot",
                "I'm unable",
                "I don't know"
            ]
        }

        if not config_path.exists():
            return default_config

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
                # Merge with defaults (prefer loaded values)
                return {**default_config, **loaded_config}
        except (json.JSONDecodeError, IOError):
            return default_config

    def validate(self, response: str, task: str = "") -> ValidationResult:
        """Run all validation rules on the response."""
        violations: list[Violation] = []
        sanitized = response

        # Run all validation rules
        violations.extend(self._check_response_length(response))
        violations.extend(self._check_code_syntax(response))

        destructive_violations, sanitized = self._check_destructive_commands(response)
        violations.extend(destructive_violations)

        violations.extend(self._check_todo_injection(response))
        violations.extend(self._check_diff_size(response))
        violations.extend(self._check_confidence_markers(response))

        # Determine if valid (no "block" severity violations)
        valid = not any(v.severity == "block" for v in violations)

        return ValidationResult(
            valid=valid,
            violations=violations,
            sanitized_response=sanitized
        )

    def _check_response_length(self, response: str) -> list[Violation]:
        """Check if response length is within acceptable bounds."""
        violations = []
        length = len(response)

        if length < self.config["min_response_length"]:
            violations.append(Violation(
                rule="response_too_short",
                severity="warn",
                message=f"Response is only {length} characters (min: {self.config['min_response_length']})"
            ))
        elif length > self.config["max_response_length"]:
            violations.append(Violation(
                rule="response_too_long",
                severity="warn",
                message=f"Response is {length} characters (max: {self.config['max_response_length']})"
            ))

        return violations

    def _check_code_syntax(self, response: str) -> list[Violation]:
        """Check syntax of code blocks in the response."""
        violations = []

        # Extract Python code blocks
        python_blocks = re.findall(r'```python\s*(.*?)```', response, re.DOTALL | re.IGNORECASE)
        for i, code in enumerate(python_blocks):
            try:
                ast.parse(code)
            except SyntaxError as e:
                violations.append(Violation(
                    rule="code_syntax_error",
                    severity="warn",
                    message=f"Python block {i+1} has syntax error: {e.msg} at line {e.lineno}"
                ))

        # Extract JavaScript code blocks (basic bracket matching)
        js_blocks = re.findall(r'```(?:javascript|js|typescript|ts)\s*(.*?)```', response, re.DOTALL | re.IGNORECASE)
        for i, code in enumerate(js_blocks):
            if not self._check_brackets_balanced(code):
                violations.append(Violation(
                    rule="code_syntax_error",
                    severity="warn",
                    message=f"JavaScript/TypeScript block {i+1} has unbalanced brackets"
                ))

        return violations

    def _check_brackets_balanced(self, code: str) -> bool:
        """Check if brackets/braces/parens are balanced."""
        stack = []
        pairs = {'(': ')', '[': ']', '{': '}'}

        for char in code:
            if char in pairs:
                stack.append(char)
            elif char in pairs.values():
                if not stack or pairs[stack.pop()] != char:
                    return False

        return len(stack) == 0

    def _check_destructive_commands(self, response: str) -> tuple[list[Violation], str]:
        """Check for destructive commands and redact them."""
        violations = []
        sanitized = response

        for pattern in self.config["destructive_patterns"]:
            matches = list(re.finditer(pattern, response, re.IGNORECASE))
            if matches:
                violations.append(Violation(
                    rule="destructive_command",
                    severity="block",
                    message=f"Contains destructive command pattern: {pattern} ({len(matches)} occurrence(s))"
                ))
                # Redact all matches
                for match in reversed(matches):  # Reverse to maintain indices
                    sanitized = (
                        sanitized[:match.start()] +
                        "[REDACTED: destructive command]" +
                        sanitized[match.end():]
                    )

        return violations, sanitized

    def _check_todo_injection(self, response: str) -> list[Violation]:
        """Check for excessive TODO/FIXME/HACK markers (hallucination indicator)."""
        violations = []

        # Count TODO-like markers
        todo_pattern = r'\b(TODO|FIXME|HACK|XXX|UNDONE)\b'
        todos = re.findall(todo_pattern, response, re.IGNORECASE)

        if len(todos) > self.config["max_todo_count"]:
            violations.append(Violation(
                rule="todo_injection",
                severity="warn",
                message=f"Found {len(todos)} TODO/FIXME markers (max: {self.config['max_todo_count']})"
            ))

        return violations

    def _check_diff_size(self, response: str) -> list[Violation]:
        """Check if code blocks exceed reasonable line count."""
        violations = []

        # Extract all code blocks
        code_blocks = re.findall(r'```.*?\n(.*?)```', response, re.DOTALL)
        total_lines = sum(len(block.split('\n')) for block in code_blocks)

        if total_lines > self.config["max_code_lines"]:
            violations.append(Violation(
                rule="diff_size_limit",
                severity="warn",
                message=f"Code blocks contain {total_lines} total lines (max: {self.config['max_code_lines']})"
            ))

        return violations

    def _check_confidence_markers(self, response: str) -> list[Violation]:
        """Check for phrases indicating AI uncertainty or delegation failure."""
        violations = []

        for phrase in self.config["confidence_phrases"]:
            if re.search(re.escape(phrase), response, re.IGNORECASE):
                violations.append(Violation(
                    rule="confidence_marker",
                    severity="warn",
                    message=f"Contains uncertainty phrase: '{phrase}'"
                ))
                break  # Only report once

        return violations


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Validate AI response before consumption")
    parser.add_argument(
        '--json',
        required=True,
        help='JSON string with "response" and optional "task" fields'
    )
    parser.add_argument(
        '--config',
        type=Path,
        help='Path to validator_config.json (default: same directory as script)'
    )

    args = parser.parse_args()

    try:
        # Parse input JSON
        input_data = json.loads(args.json)
        response = input_data.get("response", "")
        task = input_data.get("task", "")

        # Validate
        validator = ResponseValidator(config_path=args.config)
        result = validator.validate(response, task)

        # Output result as JSON
        print(json.dumps(result.to_dict(), indent=2))

    except json.JSONDecodeError as e:
        error_result = {
            "valid": False,
            "violations": [{
                "rule": "invalid_input",
                "severity": "block",
                "message": f"Failed to parse input JSON: {e}"
            }],
            "sanitized_response": ""
        }
        print(json.dumps(error_result, indent=2))
        exit(1)
    except Exception as e:
        error_result = {
            "valid": False,
            "violations": [{
                "rule": "script_error",
                "severity": "block",
                "message": f"Validation script error: {e}"
            }],
            "sanitized_response": ""
        }
        print(json.dumps(error_result, indent=2))
        exit(1)


if __name__ == "__main__":
    main()
